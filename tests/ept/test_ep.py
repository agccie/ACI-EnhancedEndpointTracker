import json, pytest, time, subprocess, traceback, inspect, re
from app.tasks.ept import utils as ept_utils
from app.tasks.ept import simulator
from app.tasks.ept.simulator import sim_queues

from app.tasks.ept import node_manager
from app.tasks.ept import ep_subscriber
from app.tasks.ept.ep_subscriber import EPSubscriber
from app.tasks.ept.ep_priority_worker import EPPriorityWorker
from app.tasks.ept.ep_worker import EPWorker
from app.tasks.ept.ep_worker import clear_fabric_endpoint
from app.tasks.ept.ep_worker import clear_node_endpoint
from app.tasks.ept.node_manager import Node_Monitor
from app.tasks.ept.ep_job import EPJob
from multiprocessing import Process

# set up simulators
sim = simulator.ApicSimulator()
connection_sim = simulator.Connection("'simulated-host'")
ept_utils.SIMULATOR = sim
ept_utils.CONNECTION_SIMULATOR = connection_sim

# static test variables
test_fabric = "fab2"
test_overlay_vnid = "16777199"

def get_subscriber(**kwargs):
    # get subscriber object with optional simulation event file
    # caller MUST execute start/stop_workers
    fab = kwargs.get("fabric", test_fabric)
    overlay = kwargs.get("overlay", test_overlay_vnid)
    event_file=kwargs.get("event_file","tests/testdata/ept/start_workers.json")
    dut = EPSubscriber(fab, overlay)

    # options user can set in kwargs for subscriber initialization
    opts = ["max_ep_events", "max_workers", "max_jobs", "analyze_move", 
            "analyze_stale", "auto_clear_stale", "analyze_offsubnet", 
            "auto_clear_offsubnet",
            "notify_stale_syslog", "notify_stale_email", "notify_move_syslog",
            "notify_move_email", "email_address", "syslog_server", 
            "syslog_port", 
            "queue_interval", "worker_hello", "worker_hello_multiplier",
            "trust_subscription", "enqueue_faule_threshold", "max_key_count",
            "wworker_disable", "pworker_disable", "transitory_stale_time",
            "transitory_xr_stale_time",
            "transitory_delete_time", "monitor_disable", "controller_interval"]
    for o in opts:
        if o in kwargs: setattr(dut, o, kwargs[o])

    sim.clear()
    if type(event_file) is list or type(event_file) is tuple:
        for f in event_file: sim.add_event_file(f)
    else:
        sim.add_event_file(event_file)
    sim.start()
    return dut

def get_worker(event_file=None):
    # get EPWorker object for simulation
    sim.clear()
    if event_file is not None: sim.add_event_file(event_file)
    sim.start()
    txQ = simulator.mQueue()
    rxQ = simulator.mQueue()
    prQ = simulator.mQueue()
    dut = EPWorker(txQ, rxQ, prQ, test_fabric, test_overlay_vnid, 0)
    return dut

def get_priority_worker(event_file=None):
    # get EPPriorityWorker object for simulation
    sim.clear()
    sim.add_event_file("tests/testdata/ept/start_workers.json")
    if event_file is not None: sim.add_event_file(event_file)
    sim.start()
    txQ = simulator.mQueue()
    rxQ = simulator.mQueue()
    prQ = simulator.mQueue()
    bcastQ = [simulator.mQueue()]
    bcastPrQ = [simulator.mQueue()]
    dut = EPPriorityWorker(txQ, rxQ, prQ, bcastQ, bcastPrQ, test_fabric,"")
    dut.init(EPJob("init", {}))
    return dut

def get_node_monitor(event_file=None):
    # get Node_Monitor object for simulation
    sim.clear()
    # always add start_workers which has required object for Node_Monitor init
    sim.add_event_file("tests/testdata/ept/start_workers.json")
    if event_file is not None: sim.add_event_file(event_file)
    sim.start()
    txQ = simulator.mQueue()
    rxQ = simulator.mQueue()
    prQ = simulator.mQueue()
    parent = EPPriorityWorker(txQ, rxQ, prQ, [], [], test_fabric,"")
    dut = Node_Monitor(test_fabric, parent)
    return dut 

def get_test_json(filename=None):
    # parse json file and return dict result - allow any exceptions
    # if no filename is provided, then assume standard format for calling 
    # function's name.
    if filename is None:
        # test filenames are the function's name without the ^test_ string 
        # present. We can use inspect module to grab caller functions name
        # and manually remove the "test_" and add appropriate path and extension
        filename = "tests/testdata/ept/%s.json" % re.sub("^test_", "", 
                        inspect.stack()[1][3])
    with open(filename, "r") as f:
        return json.load(f)

def test_ep_subscriber_stage_ep_history_db(app):
    # only a few checks performed during stage_ep_history
    #   1) example of endpoint in history that is NOT returned on refresh query
    #       should have deleted job created (only on node-101, not node-102)
    #       vnid: 3000001, ip: 10.1.1.101, node:101 (epmIpEp and Rs..Att)
    #       vnid: 15000003, mac: 00:00:00:00:00:0A, node:101
    #   2) example of endpoint NOT in history that is return on refresh query
    #       should have create job created
    #       vnid: 3000001, ip: 10.1.1.102, node:101 (epmIpEp and Rs..Att)
    #       vnid: 15000003, mac: 00:00:00:00:00:0B, node:101
    #   3) example of endpoint in history AND that is return on refresh query
    #       should have create job created
    #       vnid: 3000001, ip: 10.1.1.103, node:101 (epmIpEp and Rs..Att)
    #       vnid: 15000003, mac: 00:00:00:00:00:0C, node:101
    #   4) example of endpoint previously in history as 'deleted' and NOT 
    #       returned in refresh query should not have any job returned
    #       vnid: 3000001, ip: 10.1.1.104, node:101 
    #       vnid: 15000003, mac: 00:00:00:00:00:0D, node:101

    # import DUT classes
    sim.clear()
    sim.add_event_file("tests/testdata/ept/stage_ep_history_db_extra.json")
    sim.start()
    session = ept_utils.get_apic_session(test_fabric)
    try:
        rebuild_jobs = ep_subscriber.stage_ep_history_db(
            test_fabric,session,app,test_overlay_vnid)
        assert len(rebuild_jobs) > 0
        vrf = "3000001"
        bd = "15000003"
        rs = "epmRsMacEpToIpEpAtt"
        present = [
            {"vnid":vrf,"addr":"10.1.1.101","node":"101", "c":"epmIpEp",
                "status":"deleted"},
            {"vnid":vrf,"addr":"10.1.1.101","node":"101","c":rs,
                "status":"deleted"},
            {"vnid":bd,"addr":"00:00:00:00:00:0A","node":"101","c":"epmMacEp",
                "status":"deleted"},
            {"vnid":vrf,"addr":"10.1.1.101","node":"102", "c":"epmIpEp",
                "status":"created"},
            {"vnid":vrf,"addr":"10.1.1.101","node":"102","c":rs,
                "status":"created"},
            {"vnid":bd,"addr":"00:00:00:00:00:0A","node":"102","c":"epmMacEp",
                "status":"created"},
            {"vnid":vrf,"addr":"10.1.1.102","node":"101", "c":"epmIpEp",
                "status":"created"},
            {"vnid":vrf,"addr":"10.1.1.102","node":"101","c":rs,
                "status":"created"},
            {"vnid":bd,"addr":"00:00:00:00:00:0B","node":"101","c":"epmMacEp",
                "status":"created"},
            {"vnid":vrf,"addr":"10.1.1.103","node":"101", "c":"epmIpEp",
                "status":"created"},
            {"vnid":vrf,"addr":"10.1.1.103","node":"101","c":rs,
                "status":"created"},
            {"vnid":bd,"addr":"00:00:00:00:00:0C","node":"101","c":"epmMacEp",
                "status":"created"},          
        ]
        not_present = [
            {"vnid":vrf,"addr":"10.1.1.104","node":"101","c":"epmIpEp"},
            {"vnid":vrf,"addr":"10.1.1.104","node":"101","c":rs},
            {"vnid":bd,"addr":"00:00:00:00:00:0D","node":"102","c":"epmMacEp"},
        ]
        for j in rebuild_jobs:
            if j.data["vnid"] == vrf or j.data["vnid"] == bd:
                print "node-%s, status-%s, c-%s, vnid-%s, addr-%s" % (
                    j.data["node"], j.data["status"],
                    j.data["classname"], j.data["vnid"], j.key["addr"])

        for e in present:
            is_present = False
            for j in rebuild_jobs:
                if j.data["node"] == e["node"] and j.key["addr"] == e["addr"]\
                    and j.data["vnid"] == e["vnid"] and \
                    j.data["classname"] == e["c"]:
                    assert j.data["status"] == e["status"]
                    is_present = True
                    break
            if not is_present:
                print "%s not found in returned list" % e
                assert False

        for e in not_present:
            is_present = False
            for j in rebuild_jobs:
                if j.data["node"] == e["node"] and j.key["addr"] == e["addr"]\
                    and j.data["vnid"] == e["vnid"] and \
                    j.data["classname"] == e["c"]:
                    is_present = True
                    break
            if is_present:
                print "unexpected %s found in returned list" % e
                assert False                
                   
    finally:
        # must manually rebuild ep_history table for other tests
        with app.app_context():
            from ..conftest  import init_collection
            db = app.mongo.db
            init_collection(
                collection_name = "ep_history",
                collection = db.ep_history,
                # rebuild with folder
                jsfile = "tests/testdata/ept/ep_history",
                index = ["vnid","addr"]
            )

def test_node_manager_rebuild_name_db(app):
    # ensure expected number of entries are rebuilt from provided event file
    # expect 12 vrfs, 13 BDs, 1 external BD, 1 svcBD = 27 vnids
    # and 17 epgs
    try:
        sim.clear()
        sim.add_event_file("tests/testdata/ept/rebuild_name_db.json")
        sim.start()
        session = ept_utils.get_apic_session(test_fabric)
        assert node_manager.build_initial_name_db(test_fabric,session,app) is True
        with app.app_context():
            db = app.mongo.db
            assert db.ep_vnids.find().count() == 27
            assert db.ep_epgs.find().count() == 17
    finally:
        # must manually rebuild ep_vnids and ep_epgs if use by other tests
        with app.app_context():
            db = app.mongo.db
            from ..conftest  import init_collection
            init_collection(
                collection_name = "ep_vnids",
                collection = db.ep_vnids,
                jsfile = "tests/testdata/ept/ep_vnids.json",
                index = ["fabric", "name"]
            )
            init_collection(
                collection_name = "ep_epgs",
                collection = db.ep_epgs,
                jsfile = "tests/testdata/ept/ep_epgs.json",
                index = ["fabric", "name"]
            )

def test_node_manager_rebuild_subnets_db(app):
    # ensure expected number of entries are rebuilt from provided event file
    # fvSubnet from fvBD = 12
    #       1 15728622
    #       1 15826916
    #       1 15925206
    #       1 16023499
    #       1 16187319
    #       1 16580490
    #       1 16744307
    #       1 16777209
    #       2 15794150
    #       2 15859681
    # fvSubnet from AEPg = 3, fvIpAttr = 3 (one usefvSubnet=no is skipped)
    #       11.13.5.1/24 to uni/tn-ap/BD-ap_bd
    #       172.2.1.1/24 to uni/tn-ag/BD-bd3
    #       2001::1/64 to uni/tn-ag/BD-bd3
    #       (fvIpAttr) 172.1.1.23/31  to uni/tn-ag/BD-bd3
    #       (fvIpAttr) 172.1.1.13 (implied /32) to uni/tn-ag/BD-bd3 
    #       (fvIPAttr) 2033:ae2:22:0:1::6/39 to uni/tn-ag/BD-bd3 
    #       5 15794154
    #       + 1 15794150 (total 3 from fvBD)
    # fvSubnet from vnsEPpInfo = 1 
    #       15.1.1.1/24 to uni/tn-ag/BD-bd1 (15499165)
    #       + 1 15859681 (total 3 from fvBD)
    try:
        sim.clear()
        sim.add_event_file("tests/testdata/ept/rebuild_subnets_db.json")
        sim.start()
        session = ept_utils.get_apic_session(test_fabric)
        assert node_manager.build_initial_subnets_db( test_fabric,session,app)
        with app.app_context():
            db = app.mongo.db
            subnets = {}
            for h in db.ep_subnets.find({"fabric":test_fabric}):
                subnets[h["vnid"]] = h
            assert len(subnets) == 11
            assert len(subnets["15728622"]["subnets"]) == 1
            assert len(subnets["15826916"]["subnets"]) == 1
            assert len(subnets["15925206"]["subnets"]) == 1
            assert len(subnets["16023499"]["subnets"]) == 1
            assert len(subnets["16187319"]["subnets"]) == 1
            assert len(subnets["16580490"]["subnets"]) == 1
            assert len(subnets["16744307"]["subnets"]) == 1
            assert len(subnets["16777209"]["subnets"]) == 1
            assert len(subnets["15794150"]["subnets"]) == 3
            assert len(subnets["15859681"]["subnets"]) == 3
            assert len(subnets["15794154"]["subnets"]) == 5
            # for last entry, verify all fields correct
            for subnet in subnets["15794154"]["subnets"]:
                if subnet["ip"] == "172.2.1.1/24":
                    assert subnet["type"] == "ipv4"
                    assert int(subnet["mask"]) == 0xffffff00
                    assert int(subnet["addr"]) == 0xac020100
                elif subnet["ip"] == "172.1.1.23/31":
                    assert subnet["type"] == "ipv4"
                    assert int(subnet["mask"]) == 0xfffffffe
                    assert int(subnet["addr"]) == 0xac010116
                elif subnet["ip"] == "172.1.1.13":
                    assert subnet["type"] == "ipv4"
                    assert int(subnet["mask"]) == 0xffffffff
                    assert int(subnet["addr"]) == 0xac01010d
                elif subnet["ip"] == "2001::1/64":
                    assert subnet["type"] == "ipv6"
                    assert int(subnet["mask"]) == \
                        0xffffffffffffffff0000000000000000
                    assert int(subnet["addr"]) == \
                        0x20010000000000000000000000000000
                elif subnet["ip"] == "2033:ae2:22:0:1::6/39":
                    assert subnet["type"] == "ipv6"
                    assert int(subnet["mask"]) == \
                        0xfffffffffe0000000000000000000000
                    assert int(subnet["addr"]) == \
                        0x20330ae2000000000000000000000000
                else:
                    print "invalid/unexpected subnet!: %s" % subnet
                    assert False
    finally:
        # must manually rebuild ep_vnids and ep_epgs if use by other tests
        with app.app_context():
            db = app.mongo.db
            from ..conftest  import init_collection
            init_collection(
                collection_name = "ep_subnets",
                collection = db.ep_subnets,
                jsfile = "tests/testdata/ept/ep_subnets.json",
                index = ["fabric", "vnid"]
            )

def test_node_manager_func_get_bd_vnid_for_dn(app):
    # ensure currently parsing dn's for bd/epg and returning correct bd
    dut = get_node_monitor()
    ln1 = "uni/tn-ag/LDevInst-[uni/tn-ag/lDevVip-n7k]-ctx-v1/"
    ln1+= "G-n7kctxv1-N-bd1-C-eth9-9"
    assert "15859681" == dut.get_bd_vnid_for_dn(ln1)
    assert "16580490" == dut.get_bd_vnid_for_dn("uni/tn-ag/ap-app/epg-e2")
    assert "15925206" == dut.get_bd_vnid_for_dn("uni/tn-ty/BD-bd-y")
    # unknown epg and unknown bd
    assert dut.get_bd_vnid_for_dn("uni/tn-ty/BD-bd-does-not-exist") is None
    assert dut.get_bd_vnid_for_dn("uni/tn-ty/ap-app/epg-epg-no-exist") is None

def test_node_manager_func_handle_subnet_event_fvSubnet_created(app):
    # send create event for unknown fvSubnet and ensure it's added to db
    # subnet: uni/tn-ag/BD-bd1/subnet-[10.1.1.1/24]

    key = { "fabric":test_fabric, "subnets.ip": "10.1.1.1/24"}
    dut = get_node_monitor()
    dut.handle_subnet_event(get_test_json())
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key)    
        assert f is not None
        assert f["vnid"] == dut.get_bd_vnid_for_dn("uni/tn-ag/BD-bd1")
        assert len(f["subnets"]) == 1
        assert int(f["subnets"][0]["addr"]) == 0x0a010100

def test_node_manager_func_handle_subnet_event_fvSubnet_added(app):
    # send create event for unknown fvSubnet and ensure it's added to db
    # in this scenario, this is adding a subnet to a BD with one subnet 
    # currently present
    # subnet: uni/tn-ag/BD-bd2/subnet-[10.2.1.1/24]
    # new-subnet: uni/tn-ag/BD-bd2/subnet-[10.3.1.1/24]
    key = { "fabric":test_fabric, "subnets.ip": "10.2.1.1/24"}
    key2= { "fabric":test_fabric, "subnets.ip": "10.3.1.1/24"}
    dut = get_node_monitor()
    dut.handle_subnet_event(get_test_json())
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key)    
        assert f is not None
        assert f["vnid"] == dut.get_bd_vnid_for_dn("uni/tn-ag/BD-bd2")
        assert len(f["subnets"]) == 2
        assert int(f["subnets"][0]["addr"]) == 0x0a020100
        assert int(f["subnets"][1]["addr"]) == 0x0a030100
        f2 = db.ep_subnets.find_one(key2)
        assert f2["subnets"] == f["subnets"]

def test_node_manager_func_handle_subnet_event_fvSubnet_deleted_known(app):
    # send delete event for known fvSubnet and ensure it's removed from db
    # subnet: uni/tn-ag/BD-bd3/subnet-[10.4.1.1/24]
    #   this BD also has 10.5.1.1/24 subnet present, ensure it's not deleted
    key = { "fabric":test_fabric, "vnid": "15794154"}
    dut = get_node_monitor()
    dut.handle_subnet_event(get_test_json())
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key)    
        assert f is not None
        assert f["vnid"] == dut.get_bd_vnid_for_dn("uni/tn-ag/BD-bd3")
        assert len(f["subnets"]) == 1
        assert int(f["subnets"][0]["addr"]) == 0x0a050100

def test_node_manager_func_handle_subnet_event_fvSubnet_deleted_unknown(app):
    # send delete event for unknown fvSubnet and ensure no action
    # subnet: uni/tn-ag/BD-bd4/subnet-[10.6.1.1/24]
    key = { "fabric":test_fabric, "subnets.ip":"10.6.1.1/24"}
    dut = get_node_monitor()
    dut.handle_subnet_event(get_test_json())
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key)    
        assert f is None

def test_node_manager_func_handle_subnet_event_fvIpAttr_created(app):
    # send create event for unknown fvIpAttr and ensure it's added to db
    # uni/tn-ag/ap-app/epg-useg5/crtrn/ipattr-ip-fvIpAttr_created
    # subnet: 10.7.1.1/24
    key = { "fabric":test_fabric, "vnid":"15695754"}
    dut = get_node_monitor()
    dut.handle_subnet_event(get_test_json())
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key)    
        assert f is not None
        assert f["vnid"] == dut.get_bd_vnid_for_dn("uni/tn-ag/BD-bd5")
        assert len(f["subnets"]) == 1
        assert int(f["subnets"][0]["addr"]) == 0x0a070100

def test_node_manager_func_handle_subnet_event_fvIpAttr_deleted(app):
    # send delete event for known fvIpAttr and ensure it's removed from db
    # uni/tn-ag/ap-app/epg-useg6/crtrn/ipattr-ip-fvIpAttr_deleted
    # subnet: 10.8.1.1/24
    key = { "fabric":test_fabric, "vnid":"15695755"}
    dut = get_node_monitor()
    dut.handle_subnet_event(get_test_json())
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key)    
        assert f is not None
        assert f["vnid"] == dut.get_bd_vnid_for_dn("uni/tn-ag/BD-bd6")
        assert len(f["subnets"]) == 0

def test_node_manager_func_handle_subnet_event_fvIpAttr_modified(app):
    # send modify event for known fvIpAttr and ensure ip is updated in db
    # uni/tn-ag/ap-app/epg-useg7/crtrn/ipattr-ip-fvIpAttr_modified
    # from: 10.9.1.1/24 to 10.10.1.1/24
    key = { "fabric":test_fabric, "vnid":"15695756"}
    dut = get_node_monitor()
    dut.handle_subnet_event(get_test_json())
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key)    
        assert f is not None
        assert f["vnid"] == dut.get_bd_vnid_for_dn("uni/tn-ag/BD-bd7")
        assert len(f["subnets"]) == 1
        assert int(f["subnets"][0]["addr"]) == 0x0a0a0100

def test_node_manager_func_handle_subnet_event_fvIpAttr_usefvSubnet_known(app):
    # send modify event for fvIpAttr where usefvSubnet is set and ensure
    # previous subnet is deleted
    # uni/tn-ag/ap-app/epg-useg8/crtrn/ipattr-ip-fvIpAttr_usefvSubnet_known
    # subnet: 10.11.1.1/24
    key = { "fabric":test_fabric, "vnid":"15695757"}
    dut = get_node_monitor()
    dut.handle_subnet_event(get_test_json())
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key)    
        assert f is not None
        assert f["vnid"] == dut.get_bd_vnid_for_dn("uni/tn-ag/BD-bd8")
        assert len(f["subnets"]) == 0

def test_node_manager_func_handle_subnet_event_fvIpAttr_usefvSubnet_unknown(app):
    # send create event for fvIpAttr where usefvSubnet is set and ensure
    # no new entry is created
    # uni/tn-ag/ap-app/epg-useg9/crtrn/pattr-ip-fvIpAttr_usefvSubnet_unknown
    # subnet: 10.12.1.1/24
    key = { "fabric":test_fabric, "vnid":"15695758"}
    dut = get_node_monitor()
    dut.handle_subnet_event(get_test_json())
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key)    
        assert f is None

def test_node_manager_func_handle_subnet_event_old_event(app):
    # send delete event for fvSubnet where ts is less than current db time
    # and ensure delete is ignored
    # subnet: uni/tn-ag/BD-bd10/subnet-[10.13.1.1/24]
    key = { "fabric":test_fabric, "vnid":"15695759"}
    dut = get_node_monitor()
    dut.handle_subnet_event(get_test_json())
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key)    
        assert f is not None
        assert f["vnid"] == dut.get_bd_vnid_for_dn("uni/tn-ag/BD-bd10")
        assert len(f["subnets"]) == 1
        assert int(f["subnets"][0]["addr"]) == 0x0a0d0100

def test_node_manager_func_handle_epg_rsbd_update_move_multiple(app):
    # for single subnet on uni/tn-ag/ap-app/epg-useg11 programmed on bd-11
    # ensure that it's correctly moved to bd-12 vnid
    # ensure that old subnets remain on bd-11
    #   old-subnets: 10.13.1.1/24, 10.14.1.1/24, 10.15.1.1/24, 10.16.1.1/24
    #   only subnet: 10.14.1.1/24, 10.15.1.1/24 should move to bd-11
    # bd-11 existing subnet: 10.17.1.1/24
    key1 = { "fabric":test_fabric, "vnid":"15695760"}
    key2 = { "fabric":test_fabric, "vnid":"15695761"}
    epg = "uni/tn-ag/ap-app/epg-useg11"
    dut = get_node_monitor()
    dut.handle_epg_rsbd_update(epg, "15695761")
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key1)    
        assert f is not None
        assert len(f["subnets"]) == 2
        addr = [int(s["addr"]) for s in f["subnets"]]
        assert 0x0a0d0100 in addr
        assert 0x0a100100 in addr
        f2 = db.ep_subnets.find_one(key2)    
        assert f2 is not None
        assert len(f2["subnets"]) == 3
        addr = [int(s["addr"]) for s in f2["subnets"]]
        assert 0x0a0e0100 in addr
        assert 0x0a0f0100 in addr
        assert 0x0a110100 in addr

def test_node_manager_func_handle_epg_rsbd_update_move_none(app):
    # for subnets that match epg dn but already existing on new bd, 
    # ensure they are not moved
    # uni/tn-ag/ap-app/epg-useg12 on bd-13
    #  old-subnets: 10.18.1.1/24, 10.19.1.1/24
    key1 = { "fabric":test_fabric, "vnid":"15695762"}
    epg = "uni/tn-ag/ap-app/epg-useg12"
    dut = get_node_monitor()
    dut.handle_epg_rsbd_update(epg, "15695762")
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key1)    
        assert len(f["subnets"]) == 2
        addr = [int(s["addr"]) for s in f["subnets"]]
        assert 0x0a120100 in addr
        assert 0x0a130100 in addr

def test_node_manager_func_handle_epg_rsbd_update_move_new(app):
    # for subnets that match epg dn but destination is on bd_vnid not
    # found in ep_subnets, ensure new subnets are pushed    
    # for uni/tn-ag/ap-app/epg-useg13 on bd-14 moved to bd-15
    #   old-subnets: 10.20.1.1/24
    key1 = { "fabric":test_fabric, "vnid":"15695764"}
    epg = "uni/tn-ag/ap-app/epg-useg13"
    dut = get_node_monitor()
    dut.handle_epg_rsbd_update(epg, "15695764")
    with app.app_context():
        db = app.mongo.db
        f = db.ep_subnets.find_one(key1)    
        assert len(f["subnets"]) == 1
        addr = [int(s["addr"]) for s in f["subnets"]]
        assert 0x0a140100 in addr

def test_ep_subscriber_start_workers(app):
    # ensure all workers are sucessfully started and alive
    dut = EPSubscriber(test_fabric, test_overlay_vnid)
    sim.clear()
    sim.add_event_file("tests/testdata/ept/start_workers.json")
    sim.start()
    try:
        dut.start_workers()
        worker_count = dut.max_workers
        assert worker_count > 0
        assert len(dut.workers) == worker_count
        for w in dut.all_workers:
            assert isinstance(w["process"], Process)
            assert w["process"].is_alive()
            print "worker '%s' is alive" % w["wid"]
    finally:
        dut.stop_workers()

def test_ep_subscriber_check_worker_hello(app):
    # start workers and run 3 iterations of hellos and ensure all workers
    # are responding. Kill one worker and ensure hello check fails

    dut = EPSubscriber(test_fabric, test_overlay_vnid)
    sim.clear()
    sim.add_event_file("tests/testdata/ept/start_workers.json")
    sim.start()

    try:
        dut.queue_interval = 0.001
        dut.worker_hello = 0.003
        dut.start_workers()
        # use control_subscription which services priority queue and calls
        # check_worker_hello, then explicitly call check_worker_hello for return
        # status
        dut.control_subscription()
        assert dut.check_worker_hello
        # run for several iterations and ensure all workers are alive
        for x in xrange(0,10):
            dut.control_subscription()
            time.sleep(dut.worker_hello)
        assert dut.check_worker_hello()
        for w in dut.all_workers:
            print "wid(%s) last_hello(%f)" % (w["wid"], w["last_hello"])
            assert w["last_hello"]>0

        # kill single worker, ensure check_worker_hello detects it
        ept_utils.terminate_process(dut.wworker["process"])
        for x in xrange(0,5):
            dut.control_subscription()
            time.sleep(dut.worker_hello)
        assert not dut.check_worker_hello()
    finally:
        dut.stop_workers()
        
def test_ep_subscriber_refresh_workers_multiple_jobs(app):
    # enqueue multiple jobs on tx queue and ensure they are correctly
    # removed when put on rx queue
    
    dut = EPSubscriber(test_fabric, test_overlay_vnid)
    dut.wworker_disable = True
    dut.pworker_disable = True
    dut.workers[0] = {
        "wid": 0, "txQ": simulator.mQueue(), "rxQ": simulator.mQueue(),
        "process": None, "last_hello":0
    }
    dut.workers[1] = {
        "wid": 1, "txQ": simulator.mQueue(), "rxQ": simulator.mQueue(),
        "process": None, "last_hello":0
    }

    # add 3 job to txQ of both workers, ensure pending_jobs is 6
    jobs = {}
    for x in xrange(0,3):
        j = EPJob("test", {"key":x})
        dut.jobs[j.keystr] = {"count":1, "wid": 0}
        dut.workers[0]["txQ"].put(j)
        jobs[x] = j
    for y in xrange(3,6):
        j = EPJob("test", {"key":y})
        dut.jobs[j.keystr] = {"count":1, "wid": 1}
        dut.workers[1]["txQ"].put(j)
        jobs[y] = j
    dut.refresh_workers()
    assert dut.pending_jobs == 6

    # simulate 1 completed job from worker 0 and 2 completed from wid 1
    # should have pending jobs set to 3 and count for dut.jobs updated
    dut.workers[0]["rxQ"].put(dut.workers[0]["txQ"].get())
    dut.workers[1]["rxQ"].put(dut.workers[1]["txQ"].get())
    dut.workers[1]["rxQ"].put(dut.workers[1]["txQ"].get())
    dut.refresh_workers()
    assert dut.pending_jobs == 3
  
    # once count is 0, they keystr is removed from dut.jobs. so each job with   
    # count of 0 key is removed and each job with count of 1 still present
    assert jobs[0].keystr not in dut.jobs
    assert jobs[1].keystr in dut.jobs and \
        dut.jobs[jobs[1].keystr]["count"] == 1
    assert jobs[2].keystr in dut.jobs and \
        dut.jobs[jobs[2].keystr]["count"] == 1
    assert jobs[3].keystr not in dut.jobs
    assert jobs[4].keystr not in dut.jobs
    assert jobs[5].keystr in dut.jobs and \
        dut.jobs[jobs[5].keystr]["count"] == 1

def test_ept_handle_event_parse_objects(app):
    # ensure that handle_event correctly parses epmMacEp, epmIpEp, and 
    # epmRsMacEpToIpEpAtt events and adds event to queue

    # overwrite mQueue to use simulator mQueue so we can catch enqueued events
    try:
        ep_subscriber.mQueue = simulator.mQueue
        dut = ep_subscriber.EPSubscriber(test_fabric, test_overlay_vnid)
        dut.max_workers = 1 # only one worker to receive parsed event
        dut.pworker_disable = True  # disable priority worker for this test
        sim.clear()
        sim.add_event_file("tests/testdata/ept/handle_event_parse_objects.json")
        sim.start()
        dut.subscribe_to_objects()
        q = dut.workers[0]["txQ"]
        while not q.empty():
            job = q.get()
            # skip setter jobs
            if job.action == "setter": continue
            assert  (job.key["addr"] == "aa:bb:cc:dd:ee:ff" and \
                    job.key["type"]=="mac") or \
                    (job.key["addr"] == "10.1.1.101" and job.key["type"]=="ip")
            assert  (job.key["vnid"] == "2654208" and job.key["type"]=="ip") \
                    or \
                    (job.key["vnid"] == "15925207" and job.key["type"]=="mac")
    finally:
        from multiprocessing import Queue as mQueue 
        ep_subscriber.mQueue = mQueue

def test_ept_get_remote_node_found(app):
    # verify remote node mapping works when checking against db
    # tunnel4 on node-101 maps to remote vpc pair (103,104) = 0x00680067
    dut = get_worker()
    assert '%s' % 0x680067 == dut.get_remote_node("101", "tunnel4")

def test_ept_get_remote_node_not_found(app):
    # verify None returned for unknown tunnel mapping
    dut = get_worker()
    assert None == dut.get_remote_node("101", "tunnel99")

def test_ept_get_peer_node_found(app):
    # verify get_peer_node returns correct value mapping 
    dut = get_worker()
    assert "101" == dut.get_peer_node("102")
    assert "101" == dut.get_peer_node("102") # check logs that cache works

def test_ept_get_peer_node_not_found(app):
    # verify None is returned for node that does not have a peer
    dut = get_worker()
    assert None == dut.get_peer_node("201")

def test_ept_get_peer_node_invalid(app):
    # verify None is returned for non-existing node (or other error)
    dut = get_worker()
    assert None == dut.get_peer_node("999")

def test_ept_ep_refresh_new_mac(app):
    # refresh ep for a new MAC ep ensuring that entry is added to 
    # history table with created status and correct update returned
    # endpoint "aa:bb:cc:dd:ee:ff" does not exists in ep_history table
    key = {
        "addr": "aa:bb:cc:dd:ee:ff",
        "vnid": "15728629",
        "type":"mac",
    }
    event_file = "tests/testdata/ept/ep_refresh_new_mac.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert u

def test_ept_ep_refresh_old_mac(app):
    # refresh ep for an existing MAC ep ensuring no update to history
    # table and no update returned
    # endpoint "00:00:00:00:00:ff" already exists in ep_history at
    # same location as provided in event file
    key = {
        "addr": "00:00:00:00:00:ff",
        "vnid": "15728629",
        "type":"mac",
    }
    event_file = "tests/testdata/ept/ep_refresh_old_mac.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert not u

def test_ept_ep_refresh_timeout_mac(app):
    # refresh ep for an existing MAC where entry has timed out for one
    # node and exists on other nodes.  history table should be updated
    # with a deleted action and correct update returned
    # endpoint 00:00:00:00:01:ff exists in ep_history for node-101 and
    # node-102.  event_file returns same state for node-101 but no 
    # state for node-102
    key = {
        "addr": "00:00:00:00:01:ff",
        "vnid": "15728629",
        "type":"mac",
    }
    event_file = "tests/testdata/ept/ep_refresh_timeout_mac.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert u

def test_ept_ep_refresh_move_mac_port(app):
    # refresh ep for an existing MAC which has moved to different port
    # history table should be updated and correct update returned
    # endpoint 00:00:00:00:02:ff exits in ep_history on node-101 port
    # eth1/4.  event file returns same endpoint on port eth1/5
    key = {
        "addr": "00:00:00:00:02:ff",
        "vnid": "15728629",
        "type":"mac",
    }
    event_file = "tests/testdata/ept/ep_refresh_move_mac_port.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert u

def test_ept_ep_refresh_move_mac_node(app):
    # refresh ep for an existing MAC which has moved to different node
    # history table should be updated and correct update returned
    # endpoint 00:00:00:00:03:ff exists in ep_history on node-101 and
    # event file returns same endpoint on node 102 port eth1/4
    key = {
        "addr": "00:00:00:00:03:ff",
        "vnid": "15728629",
        "type":"mac",
    }
    event_file = "tests/testdata/ept/ep_refresh_move_mac_node.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert u

def test_ept_ep_refresh_move_mac_encap(app):
    # refresh ep for an existing MAC which has moved to different encap
    # history table should be updated and correct update returned
    # endpoint 00:00:00:00:04:ff exists in ep_history on node-101 encap
    # vlan-101.  event file returns same endpoint with encap vlan-102 
    # and different pcTag
    key = {
        "addr": "00:00:00:00:04:ff",
        "vnid": "15728629",
        "type":"mac",
    }
    event_file = "tests/testdata/ept/ep_refresh_move_mac_encap.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert u

def test_ept_ep_refresh_new_ip(app):
    # refresh ep for a new IP ep ensuring that entry is added to 
    # history table with created status and correct update returned
    # endpoint 10.1.1.101 does not currently exist in ep_history table
    # event file returns entry on nodes 101, 102, 103, and 104
    key = {
        "addr": "10.1.1.101",
        "vnid": "2654208",
        "type":"ip",
    }
    event_file = "tests/testdata/ept/ep_refresh_new_ip.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert u

def test_ept_ep_refresh_old_ip(app):
    # refresh ep for an existing IP ep ensuring no update to history
    # table and empty update returned
    # endpoint 10.1.1.102 already exists in ep_history table and 
    # event file returns same information
    key = {
        "addr": "10.1.1.102",
        "vnid": "2654208",
        "type":"ip",
    }
    event_file = "tests/testdata/ept/ep_refresh_old_ip.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert not u

def test_ept_ep_refresh_timeout_ip(app):
    # refresh ep for an existing IP where entry has timed out on remote
    # nodes and exists on other nodes.  history table should be updated
    # with a deleted action and correct update returned
    # endpoint 10.1.1.103 already exists in ep_history table local to 
    # nodes 101 and 102 and remote on nodes 103 and node 104.  event file
    # returns same info without any state on node 103 and node 104
    key = {
        "addr": "10.1.1.103",
        "vnid": "2654208",
        "type":"ip",
    }
    event_file = "tests/testdata/ept/ep_refresh_timeout_ip.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert u

def test_ept_ep_refresh_move_ip_node(app):
    # refresh ep for an existing IP which has moved to different node
    # history table should be updated and correct update returned
    # endpoint 10.1.1.104 already exists in ep_history table local to
    # nodes 101 and 102 and remote on nodes 103 and node 104.  event 
    # file returns endpoint move to vpc pair 103+104 (local on node
    # 103 and node 104 and remote on node 101 and node 102)
    key = {
        "addr": "10.1.1.104",
        "vnid": "2654208",
        "type":"ip",
    }
    event_file = "tests/testdata/ept/ep_refresh_move_ip_node.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert u

def test_ept_ep_refresh_move_ip_mac(app):
    # refresh ep for an existing IP which has moved to different MAC.
    # history table should be updated and correct update returned
    # endpoint 10.1.1.105 already exists in ep_history table local to
    # node 101 and 102 and remote on nodes 103 and node 104.  The mac
    # for epmRsMacEpToIpEpAtt changes to new MAC in event file
    key = {
        "addr": "10.1.1.105",
        "vnid": "2654208",
        "type":"ip",
    }
    event_file = "tests/testdata/ept/ep_refresh_move_ip_mac.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert u

def test_ept_ep_refresh_double_delete(app):
    # refresh ep for an existing IP which has a deleted entry already in 
    # database and refreshed value does not return node with previously
    # deleted entry
    # endpoint 10.1.1.106 already exists in ep_history with deleted status
    # on node 102 and present on node-101. event file contains same 
    # value on node-101 so no update should be seen
    key = {
        "addr": "10.1.1.106",
        "vnid": "2654208",
        "type":"ip",
    }
    event_file = "tests/testdata/ept/ep_refresh_double_delete.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert not u

def test_ept_ep_refresh_full_delete(app):
    # refresh ep for an existing IP that no longer exists on any node
    # endpoint 10.1.1.107 already exists in ep_history on node-101 and 
    # node-102.  event file contains no value so update contains delete
    # on both nodes
    key = {
        "addr": "10.1.1.107",
        "vnid": "2654208",
        "type":"ip",
    }
    event_file = "tests/testdata/ept/ep_refresh_full_delete.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert u

def test_ept_ep_refresh_new_job_ts(app):
    # refresh an existing endpoint with ts newer than all history events
    # should return single update
    # endpoint 10.1.1.108 already exists in ep_history on node-101 and
    # event file contains a new interface to force an update
    key = {
        "addr": "10.1.1.108",
        "vnid": "2654208",
        "type":"ip",
    }
    event_file = "tests/testdata/ept/ep_refresh_new_job_ts.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert u

def test_ept_ep_refresh_old_job_ts(app):
    # refresh an existing endpoint with ts older than all history events
    # should return no updates
    # endpoint 10.1.1.109 already exists in ep_history on node-101 and
    # event file contains a new interface to force an update. however, 
    # since job_ts is older than existing history event update is ignored
    key = {
        "addr": "10.1.1.109",
        "vnid": "2654208",
        "type":"ip",
    }
    event_file = "tests/testdata/ept/ep_refresh_old_job_ts.json"
    dut = get_worker(event_file)
    (u,a) = dut.ep_refresh(key)
    assert not u

def test_ept_ep_analyze_stale_not_stale_orphan(app):
    # analyze ep in ep_history table that is not stale. empty update
    # should be returned
    # host 10.1.2.101 is orphan port on node-101 with all remote nodes
    # correctly pointing to node-101.
    key = {
        "addr": "10.1.2.101",
        "vnid": "2654208",
        "type":"ip",
    }
    dut = get_worker()
    dut.stale_double_check = False  # don't double-refresh data
    updates = dut.ep_analyze_stale(key)
    assert len(updates) == 0

def test_ept_ep_analyze_stale_not_stale_orphan_bounce(app):
    # analyze ep in ep_history table that is not stale. empty update
    # should be returned
    # host 10.1.2.102 is orphan port on node-101 with node-103 correctly
    # pointing to node-101 with bounce entry and node-104 pointing to node-103
    key = {
        "addr": "10.1.2.102",
        "vnid": "2654208",
        "type":"ip",
    }
    dut = get_worker()
    dut.stale_double_check = False  # don't double-refresh data
    updates = dut.ep_analyze_stale(key)
    assert len(updates) == 0

def test_ept_ep_analyze_stale_new_stale_orphan(app):
    # analyze ep for stale entry currently in ep_history table and
    # not in ep_stale table. ep_stale table should be updated and correct
    # update returned
    # host 10.1.2.103 is orphan port on node-101 with node-104 pointing
    # to incorrect remote node (that does not contain any entry)
    key = {
        "addr": "10.1.2.103",
        "vnid": "2654208",
        "type":"ip",
    }
    dut = get_worker()
    dut.stale_double_check = False  # don't double-refresh data
    updates = dut.ep_analyze_stale(key)
    assert len(updates) == 1
    assert "104" in updates

def test_ept_ep_analyze_stale_not_stale_vpc(app):
    # analyze ep in ep_history table that is not stale. empty update
    # should be returned
    # host 10.1.2.104 is vpc port on node-101+102 with all remote nodes
    # correctly pointing to vpc pair
    key = {
        "addr": "10.1.2.104",
        "vnid": "2654208",
        "type":"ip",
    }
    dut = get_worker()
    dut.stale_double_check = False  # don't double-refresh data
    updates = dut.ep_analyze_stale(key)
    assert len(updates) == 0

def test_ept_ep_analyze_stale_not_stale_vpc_bounce(app):
    # analyze ep in ep_history table that is not stale. empty update
    # should be returned
    # host 10.1.2.105 is vpc port on node-101+102 with node-103 correctly
    # pointing to vpc pair with bounce entry and node-104 pointing to node-103
    key = {
        "addr": "10.1.2.105",
        "vnid": "2654208",
        "type":"ip",
    }
    dut = get_worker()
    dut.stale_double_check = False  # don't double-refresh data
    updates = dut.ep_analyze_stale(key)
    assert len(updates) == 0

def test_ept_ep_analyze_stale_new_stale_vpc(app):
    # analyze ep for stale entry currently in ep_history table and
    # not in ep_stale table. ep_stale table should be updated and correct
    # update returned
    # host 10.1.2.106 is vpc port on node-101+102 with node-104 pointing
    # to incorrect remote node
    key = {
        "addr": "10.1.2.106",
        "vnid": "2654208",
        "type":"ip",
    }
    dut = get_worker()
    dut.stale_double_check = False  # don't double-refresh data
    updates = dut.ep_analyze_stale(key)
    assert len(updates) == 1
    assert "104" in updates

def test_ept_ep_analyze_stale_old_stale(app):
    # analyze ep for stale entry currently in ep_history table and
    # currently in ep_stale table. No update should occur
    # host 10.1.2.107 is vpc port on node-101+102 with node-104 pointing
    # to incorrect remote node
    key = {
        "addr": "10.1.2.107",
        "vnid": "2654208",
        "type":"ip",
    }
    dut = get_worker()
    dut.stale_double_check = False  # don't double-refresh data
    updates = dut.ep_analyze_stale(key)
    assert len(updates) == 0

def test_ept_ep_analyze_stale_no_bounce_flag(app):
    # analyze ep in ep_history table that is stale. ep_stale table should be
    # updated and correct update returned
    # host 10.1.2.108 is vpc port on node-101+102 with node-103 correctly
    # pointing to vpc pair but no bounce entry set, and node-104 pointing to 
    # node-103
    key = {
        "addr": "10.1.2.108",
        "vnid": "2654208",
        "type":"ip",
    }
    dut = get_worker()
    dut.stale_double_check = False  # don't double-refresh data
    updates = dut.ep_analyze_stale(key)
    assert len(updates) == 1
    assert "104" in updates

def test_ept_ep_analyze_stale_verify_is_stale_flag(app):
    # analyze ep for stale entry currently in ep_history table and
    # not in ep_stale table. this function only checks that is_stale flag
    # is correctly set on all nodes.
    # host 10.1.2.109 is vpc port on node-101+102 with node-104 pointing
    # to incorrect remote node.  is_stale should be True on node-104 and 
    # false on nodes 101, 102, and 103
    key = {
        "addr": "10.1.2.109",
        "vnid": "2654208",
        "type":"ip",
    }
    dut = get_worker()
    dut.stale_double_check = False  # don't double-refresh data
    updates = dut.ep_analyze_stale(key)
    assert len(updates) == 1
    assert "104" in updates
    with app.app_context():
        db = app.mongo.db
        key["fabric"] = test_fabric
        nodes =  db.ep_history.find(key)
        for f in nodes:
            assert "is_stale" in f
            if f["node"] == "101":
                assert f["is_stale"] is False
            elif f["node"] == "102":
                assert f["is_stale"] is False
            elif f["node"] == "104":
                assert f["is_stale"] is True
            else:
                print "unexpected node: %s" % f["node"]
                assert False

def test_ept_ep_analyze_stale_no_local(app):
    # analyze ep for stale entry currently in ep_history table and
    # not in ep_stale table. 
    # host 10.1.2.110 is XR on node-104 pointing to node-103 which has
    # bounce to VTEP of node-101 and node-102. However, node 101 and 
    # node 102 do not have entry present, making all XR entries stale
    key = {
        "addr": "10.1.2.110",
        "vnid": "2654208",
        "type":"ip",
    }
    dut = get_worker()
    dut.stale_double_check = False  # don't double-refresh data
    updates = dut.ep_analyze_stale(key)
    assert len(updates) == 2
    assert "103" in updates
    assert "104" in updates



def test_ept_add_fabric_event(app):
    # execute add_fabric_event and read results to ensure it is updated
    assert ept_utils.add_fabric_event(test_fabric, "new-status", "test status")
    with app.app_context():
        db = app.mongo.db
        f = db.ep_settings.find_one({"fabric":test_fabric})
        assert f is not None
        assert "fabric_events" in f
        event = f["fabric_events"][0]
        assert "ts" in event and "status" in event and "description" in event
        assert event["status"] == "new-status"
        assert "fabric_events_count" in f
        old_count = f["fabric_events_count"]
        assert ept_utils.add_fabric_event(test_fabric, "next-status","")
        f = db.ep_settings.find_one({"fabric":test_fabric})
        assert old_count + 1 == f["fabric_events_count"]

def test_ept_handle_name_event_new_ctx(app):
    # create event for a new ctx dn and verify it's added to database
    # Ctx = eptC1 with vnid 2500001 and pcTag 32770
    name = "uni/tn-common/ctx-eptC1"
    event = {
        "imdata":[{"fvCtx":{"attributes":{"dn":name}}}],
        "_ts": 5000000000
    }
    event_file = "tests/testdata/ept/handle_name_event_new_ctx.json"
    dut = get_node_monitor(event_file)
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_vnids.find_one({"fabric":test_fabric,"name":name})
        assert f is not None
        assert f["vnid"] == "2500001"
        assert f["vrf"] == "2500001"
        assert f["pcTag"] == "32770"

def test_ept_handle_name_event_update_ctx(app):
    # create event for an existing ctx dn and verify it's updated in database
    # Ctx = uni/tn-ag/ctx-v1, vnid 2654208, pcTag = 16386 updated to 27
    name = "uni/tn-ag/ctx-v1"
    event = {
        "imdata":[{"fvCtx":{"attributes":{"dn":name}}}],
        "_ts": 5000000000
    }
    event_file = "tests/testdata/ept/handle_name_event_update_ctx.json"
    dut = get_node_monitor(event_file)
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_vnids.find_one({"fabric":test_fabric,"name":name})
        assert f is not None
        assert f["vnid"] == "2654208"
        assert f["vrf"] == "2654208"
        assert f["pcTag"] == "27"

def test_ept_handle_name_event_delete_ctx(app):
    # create event for a deleted ctx dn and veriy it's removed from database
    # Ctx = uni/tn-ag/ctx-v2, empty update received
    name = "uni/tn-ag/ctx-v2"
    event = {
        "imdata":[{"fvCtx":{"attributes":{"dn":name}}}],
        "_ts": 5000000000
    }
    event_file = "tests/testdata/ept/handle_name_event_delete_ctx.json"
    dut = get_node_monitor(event_file)
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_vnids.find_one({"fabric":test_fabric,"name":name})
        assert f is None

def test_ept_handle_name_event_new_bd(app):
    # create event for a new bd and ensure entry is added to database
    # fvBD = "uni/tn-ag/BD-bd5", vnid 14680100, pcTag 60001
    name = "uni/tn-ag/BD-bd5"
    event = {
        "imdata":[{"fvBD":{"attributes":{"dn":name}}}],
        "_ts": 5000000000
    }
    event_file = "tests/testdata/ept/handle_name_event_new_bd.json"
    dut = get_node_monitor(event_file)
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_vnids.find_one({"fabric":test_fabric,"name":name})
        assert f is not None
        assert f["vnid"] == "14680100"
        assert f["vrf"] == "2500001"
        assert f["pcTag"] == "60001"

def test_ept_handle_name_event_new_ext_bd(app):
    # create event for a new ext_bd and ensure entry is added to database
    # l3extExtEncapAllocator = "uni/tn-ag/out-out1/encap-[vlan-101]", 
    # vnid 14680101, pcTag (none), encap 101
    name = "uni/tn-ag/out-out1/encap-[vlan-101]"
    event = {
        "imdata":[{"l3extExtEncapAllocator":{"attributes":{"dn":name}}}],
        "_ts": 5000000000
    }
    event_file = "tests/testdata/ept/handle_name_event_new_ext_bd.json"
    dut = get_node_monitor(event_file)
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_vnids.find_one({"fabric":test_fabric,"name":name})
        assert f is not None
        assert f["vnid"] == "14680101"
        assert f["vrf"] == ""
        assert f["pcTag"] == ""
        assert f["encap"] == "vlan-101"

def test_ept_handle_name_event_new_epg(app):
    # create event for a new epg and ensure entry is added to database
    # fvAEPg = "uni/tn-ag/ap-app/epg-e5", vnid = 2654208, pcTag = 60101
    name = "uni/tn-ag/ap-app/epg-e5"
    event = {
        "imdata":[{"fvAEPg":{"attributes":{"dn":name}}}],
        "_ts": 5000000000
    }
    event_file = "tests/testdata/ept/handle_name_event_new_epg.json"
    dut = get_node_monitor(event_file)
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_epgs.find_one({"fabric":test_fabric,"name":name})
        assert f is not None
        assert f["vnid"] == "2654208"
        assert f["pcTag"] == "60101"

def test_ept_handle_name_event_old_epg(app):
    # create event for an old epg with no change to current state and
    # ensure database is not updated
    # fvAEPg = "uni/tn-ag/ap-app/epg-e4", vnid = 2654208, pcTag = 32772
    name = "uni/tn-ag/ap-app/epg-e4"
    event = {
        "imdata":[{"fvAEPg":{"attributes":{"dn":name}}}],
        "_ts": 5000000000
    }
    event_file = "tests/testdata/ept/handle_name_event_old_epg.json"
    dut = get_node_monitor(event_file)
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_epgs.find_one({"fabric":test_fabric,"name":name})
        assert f is not None
        assert f["vnid"] == "2654208"
        assert f["pcTag"] == "32772"

def test_ept_handle_name_event_update_epg(app):
    # create event for an exiting epg with change to current state and
    # ensure database is updated with new pcTag and vrf (old 2654208, 49153)
    # fvAEPg = "uni/tn-ag/ap-app/epg-e1", vnid = 2500001, pcTag = 60103
    name = "uni/tn-ag/ap-app/epg-e1"
    event = {
        "imdata":[{"fvAEPg":{"attributes":{"dn":name}}}],
        "_ts": 5000000000
    }
    event_file = "tests/testdata/ept/handle_name_event_update_epg.json"
    dut = get_node_monitor(event_file)
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_epgs.find_one({"fabric":test_fabric,"name":name})
        assert f is not None
        assert f["vnid"] == "2500001"
        assert f["pcTag"] == "60103"

def test_ept_handle_name_event_late_epg(app):
    # create event for an existing epg with timestamp older than db entry
    # fvAEPg = "uni/tn-ag/ap-app/epg-e3", vnid = 2654208, pcTag = 49158
    # (no refresh data as should not be checked)
    name = "uni/tn-ag/ap-app/epg-e3"
    event = {
        "imdata":[{"fvAEPg":{"attributes":{"dn":name}}}],
        "_ts": 100
    }
    dut = get_node_monitor()
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_epgs.find_one({"fabric":test_fabric,"name":name})
        assert f is not None
        assert f["vnid"] == "2654208"
        assert f["pcTag"] == "49158"

def test_ept_handle_name_event_new_ext_epg(app):
    # create event for a new external epg and ensure entry is added to db
    # l3extInstP = "uni/tn-ag/out-out1/instP-out" vnid = 2654208, pcTag=60102
    name = "uni/tn-ag/out-out1/instP-out"
    event = {
        "imdata":[{"l3extInstP":{"attributes":{"dn":name}}}],
        "_ts": 5000000000
    }
    event_file = "tests/testdata/ept/handle_name_event_new_ext_epg.json"
    dut = get_node_monitor(event_file)
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_epgs.find_one({"fabric":test_fabric,"name":name})
        assert f is not None
        assert f["vnid"] == "2654208"
        assert f["pcTag"] == "60102"

def test_ept_handle_name_event_update_epg_bd(app):
    # create event for AEPg vrf change via new BD association (fvRsBd)
    # and ensure database is updated with new vnid - also ensure bd_vnid is 
    # updated
    # fvAEPg = "uni/tn-ag/ap-app/epg-e2" old vnid = 2654209, new vnid 2654208
    # and new pcTag 60104, new bd_vnid =15859681  (BD-bd1)
    name = "uni/tn-ag/ap-app/epg-e2"
    event = {
        "imdata":[{"fvRsBd":{"attributes":{"dn":"%s/rsbd" % name}}}],
        "_ts": 5000000000
    }
    event_file = "tests/testdata/ept/handle_name_event_update_epg_bd.json"
    dut = get_node_monitor(event_file)
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_epgs.find_one({"fabric":test_fabric,"name":name})
        assert f is not None
        assert f["vnid"] == "2654208"
        assert f["pcTag"] == "60104"
        assert f["bd_vnid"] == "15859681"

def test_ept_handle_named_event_update_epg_preserve_bd_vnid(app):
    # ensure that when attribute event on epg is updated, bd_vnid is
    # preseved for the epg
    # fvAEPg = "uni/tn-ag/ap-app/epg-e2" matchT old AtleastOne, new All
    # and bd_vnid stays at bd1 16580490
    name = "uni/tn-ag/ap-app/epg-e2"
    event = {
        "imdata":[{"fvAEPg":{"attributes":{"dn":"%s" % name,
            "status":"modified", "matchT":"All"}}}],
        "_ts": 5000000000
    }
    event_file = "tests/testdata/ept/"
    event_file+= "handle_name_event_update_epg_preserve_bd_vnid.json"
    dut = get_node_monitor(event_file)
    dut.handle_name_event(event)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_epgs.find_one({"fabric":test_fabric,"name":name})
        assert f is not None
        assert f["vnid"] == "2654209"
        assert f["pcTag"] == "32771"
        assert f["bd_vnid"] == "16580490"

def test_ep_worker_func_ep_handle_event_create_unknown_mac_ep(app):
    # ensure new event is added to ep_history for unknown mac 
    # and analysis required
    # mac: (2654208/15007713/00:00:00:00:00:01)
    classname = "epmMacEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True

def test_ep_worker_func_ep_handle_event_modify_unknown_mac_ep(app):
    # ensure new event is NOT added to ep_history for unknown mac on modify 
    # and no analysis required
    # mac: (2654208/15007713/00:00:00:00:00:02)
    classname = "epmMacEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_delete_unknown_mac_ep(app):
    # ensure new event is NOT added to ep_history for unknown mac on delete
    # and no analysis required
    # unknown mac: (2654208/15007713/00:00:00:00:00:03)
    classname = "epmMacEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_create_known_mac_ep(app):
    # ensure new event is added to ep_history for different mac attr on create
    # event and anaylsis is required
    # mac: (2654208/15007713/00:00:00:00:00:04)
    classname = "epmMacEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True

def test_ep_worker_func_ep_handle_event_create_known_mac_ep_no_diff(app):
    # ensure new event is NOT added to ep_history for same mac attr on create
    # event and anaylsis is not required
    # mac: (2654208/15007713/00:00:00:00:00:05)
    classname = "epmMacEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_modify_known_mac_ep(app):
    # ensure new event is added to ep_history for known mac on modify and
    # old attributes are preserved.  Analysis is required
    # mac: (2654208/15007713/00:00:00:00:00:06)
    # only flags and ts field should have changed. status is modified
    classname = "epmMacEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True
    with app.app_context():
        db = app.mongo.db
        f = db.ep_history.find_one({"fabric":test_fabric,"node":"101",
            "addr":"00:00:00:00:00:06", "vnid":"15007713"})
        assert len(f["events"])>=2
        old = f["events"][1]
        new = f["events"][0]
        for attr in old:
            if attr == "ts":
                assert new[attr] > old[attr]
            elif attr == "flags":
                assert new[attr] != old[attr]
            elif attr == "status":
                assert new[attr] == "modified"
            else:
                assert new[attr] == old[attr]

def test_ep_worker_func_ep_handle_event_modify_deleted_mac_ep(app):
    # ensure NO event is added to history on modify if last event was delete
    # and no analysis required
    # mac: (2654208/15007713/00:00:00:00:00:07)
    classname = "epmMacEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_delete_known_mac_ep(app):
    # ensure new event is added to ep_history for known mac on delete and
    # all delete attributes are set.  analysis required
    # mac: (2654208/15007713/00:00:00:00:00:08)
    classname = "epmMacEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True
    with app.app_context():
        db = app.mongo.db
        f = db.ep_history.find_one({"fabric":test_fabric,"node":"101",
            "addr":"00:00:00:00:00:08", "vnid":"15007713"})
        assert len(f["events"])>=2
        new = f["events"][0]
        assert new["status"] == "deleted"
        for a in ["ifId", "pcTag", "remote", "encap", "flags"]:
            assert new[a] == ""

def test_ep_worker_func_ep_handle_event_delete_deleted_mac_ep(app):
    # ensure NO event is added to history on delete if last event was delete
    # and no analysis required
    # mac: (2654208/15007713/00:00:00:00:00:09)
    classname = "epmMacEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_create_unknown_local_ip_ep(app):
    # ensure new event is added to ep_history for unknown local ip
    # no rewrite info at this time for local endpoint = no analyze
    # ip: (2654208/15007713/10.1.3.101)
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is False

def test_ep_worker_func_ep_handle_event_create_unknown_remote_ip_ep(app):
    # ensure new event is added to ep_history for unknown remote ip
    # ip: (2654208/15007713/10.1.3.102)
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True

def test_ep_worker_func_ep_handle_event_modify_unknown_ip_ep(app):
    # ensure new event is NOT added to ep_history for unknown ip on modify 
    # ip: (2654208/15007713/10.1.3.103)
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_delete_unknown_ip_ep(app):
    # ensure new event is NOT added to ep_history for unknown ip on delete
    # ip: (2654208/15007713/10.1.3.104)
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_create_known_local_ip_ep(app):
    # ensure new event is added to ep_history for different ip attr on create
    # event. ensure that rewrite info is preserved
    # ip: (2654208/15007713/10.1.3.105)
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True
    with app.app_context():
        db = app.mongo.db
        f = db.ep_history.find_one({"fabric":test_fabric,"node":"101",
            "addr":"10.1.3.105", "vnid":"2654208"})
        assert len(f["events"])>=2
        new = f["events"][0]
        old = f["events"][1]
        assert new["rw_mac"] == old["rw_mac"]
        assert new["rw_bd"] == old["rw_bd"]

def test_ep_worker_func_ep_handle_event_create_known_remote_ip_ep(app):
    # ensure new event is added to ep_history for different ip attr on create
    # event. ensure that rewrite info is preserved
    # ip: (2654208/15007713/10.1.3.106)
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True
    with app.app_context():
        db = app.mongo.db
        f = db.ep_history.find_one({"fabric":test_fabric,"node":"101",
            "addr":"10.1.3.106", "vnid":"2654208"})
        assert len(f["events"])>=2
        new = f["events"][0]
        old = f["events"][1]
        assert new["rw_mac"] == old["rw_mac"]
        assert new["rw_bd"] == old["rw_bd"]

def test_ep_worker_func_ep_handle_event_modify_known_ip_ep(app):
    # ensure new event is added to ep_history for known ip on modify and
    # old attributes are preserved
    # ip: (2654208/15007713/10.1.3.107)
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True
    with app.app_context():
        db = app.mongo.db
        f = db.ep_history.find_one({"fabric":test_fabric,"node":"101",
            "addr":"10.1.3.107", "vnid":"2654208"})
        assert len(f["events"])>=2
        old = f["events"][1]
        new = f["events"][0]
        for attr in old:
            if attr == "ts":
                assert new[attr] > old[attr]
            elif attr == "flags":
                assert new[attr] != old[attr]
            elif attr == "status":
                assert new[attr] == "modified"
            else:
                assert new[attr] == old[attr]

def test_ep_worker_func_ep_handle_event_modify_deleted_ip_ep(app):
    # ensure NO event is added to history on modify if last event was delete
    # ip: (2654208/15007713/10.1.3.108)
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_delete_known_ip_ep(app):
    # ensure new event is added to ep_history for known ip on delete and
    # all delete attributes are set.  ensure rewrite info is preserved
    # ip: (2654208/15007713/10.1.3.109)
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True
    with app.app_context():
        db = app.mongo.db
        f = db.ep_history.find_one({"fabric":test_fabric,"node":"101",
            "addr":"10.1.3.109", "vnid":"2654208"})
        assert len(f["events"])>=2
        new = f["events"][0]
        old = f["events"][1]
        assert new["rw_mac"] == old["rw_mac"]
        assert new["rw_bd"] == old["rw_bd"]

def test_ep_worker_func_ep_handle_event_delete_deleted_ip_ep(app):
    # ensure NO event is added to history on delete if last event was delete
    # ip: (2654208/15007713/10.1.3.110)
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_create_unknown_rw_ep(app):
    # ensure new event is added to ep_history for unknown rewrite info
    # only rewrite info should be set
    # ip: (2654208/15007713/10.1.3.111, rw_mac: 00:00:00:00:00:aa)
    classname = "epmRsMacEpToIpEpAtt"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is False
    with app.app_context():
        db = app.mongo.db
        f = db.ep_history.find_one({"fabric":test_fabric,"node":"101",
            "addr":"10.1.3.111", "vnid":"2654208"})
        assert len(f["events"])==1
        assert f["events"][0]["rw_mac"] == "00:00:00:00:00:aa"

def test_ep_worker_func_ep_handle_event_modify_unknown_rw_ep(app):
    # ensure new event is NOT added to ep_history for unknown rw on modify 
    # ip: (2654208/15007713/10.1.3.112, rw_mac: 00:00:00:00:00:aa)
    # note, test is theoretical only, should never get a modify for rewrite
    classname = "epmRsMacEpToIpEpAtt"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_delete_unknown_rw_ep(app):
    # ensure new event is NOT added to ep_history for unknown rw on delete
    # ip: (2654208/15007713/10.1.3.113, rw_mac: 00:00:00:00:00:aa)
    classname = "epmRsMacEpToIpEpAtt"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_create_known_rw_same_ep(app):
    # ensure new NO event is added to ep_history for same rw attr on create
    # event.
    # ip: (2654208/15007713/10.1.3.114, rw_mac: 00:00:00:00:00:aa,
    #                               old_rw_mac: 00:00:00:00:00:aa)
    classname = "epmRsMacEpToIpEpAtt"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is False
    assert analyze is False

def test_ep_worker_func_ep_handle_event_create_known_rw_diff_ep(app):
    # ensure new event is added to ep_history for different rw attr on create
    # event. ensure that all other attributes are maintained
    # ip: (2654208/15007713/10.1.3.115, rw_mac: 00:00:00:00:00:bb,
    #                               old_rw_mac: 00:00:00:00:00:aa)
    classname = "epmRsMacEpToIpEpAtt"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True
    with app.app_context():
        db = app.mongo.db
        f = db.ep_history.find_one({"fabric":test_fabric,"node":"101",
            "addr":"10.1.3.115", "vnid":"2654208"})
        assert len(f["events"])>=2
        new = f["events"][0]
        old = f["events"][1]
        assert new["rw_mac"] == "00:00:00:00:00:bb"
        for attr in old:
            if attr == "ts":
                assert new[attr] > old[attr]
            elif attr == "rw_mac" or attr=="rw_bd": continue
            else:
                assert new[attr] == old[attr]

def test_ep_worker_func_ep_handle_event_delete_known_rw_ep(app):
    # ensure new event is added to ep_history for rw delete and all other
    # attributes from ip are maintained
    # ip: (2654208/15007713/10.1.3.116, old_rw_mac: 00:00:00:00:00:aa)
    classname = "epmRsMacEpToIpEpAtt"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is False
    with app.app_context():
        db = app.mongo.db
        f = db.ep_history.find_one({"fabric":test_fabric,"node":"101",
            "addr":"10.1.3.116", "vnid":"2654208"})
        assert len(f["events"])>=2
        new = f["events"][0]
        old = f["events"][1]
        assert new["rw_mac"] == ""
        assert new["rw_bd"] == ""
        assert old["rw_mac"] == "00:00:00:00:00:aa"
        for attr in old:
            if attr == "ts":
                assert new[attr] > old[attr]
            elif attr == "rw_mac" or attr=="rw_bd": continue
            else:
                assert new[attr] == old[attr]

def test_ep_worker_func_ep_handle_event_create_vpc_peer_attach_ep(app):
    # ensure new event is added for vpc_peer_attach and remote is correctly
    # set to node's vpc peer (flags will say 'local')
    # ip: (2654208/15007713/10.1.3.117, rw_mac: 00:00:00:00:00:aa)
    # flags: ip,mac,peer-attached
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True
    with app.app_context():
        db = app.mongo.db
        f = db.ep_history.find_one({"fabric":test_fabric,"node":"101",
            "addr":"10.1.3.117", "vnid":"2654208"})
        assert f["events"][0]["remote"] == "102"

def test_ep_worker_func_ep_handle_event_modify_pcTag_known_ip_ep(app):
    # ensure new event is added to ep_history for known ip on modify and
    # old attributes are preserved - for event where only pcTag is updated
    # ensure that epg_name is updated to new pcTag
    # ip: (2654208/15007713/10.1.3.118, pcTag: 49153}
    # new pcTag: 32772
    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    (update, analyze) = dut.ep_handle_event(pevent)
    assert update is True
    assert analyze is True
    with app.app_context():
        db = app.mongo.db
        f = db.ep_history.find_one({"fabric":test_fabric,"node":"101",
            "addr":"10.1.3.118", "vnid":"2654208"})
        assert len(f["events"])>=2
        old = f["events"][1]
        new = f["events"][0]
        assert new["ts"] > old["ts"]
        assert new["epg_name"] != old["epg_name"]
        assert old["pcTag"] == "49153"
        assert new["pcTag"] == "32772"

def test_ep_worker_func_get_last_events_no_local(app):
    # ensure empty list returned when no previous local events
    dut = get_worker()
    last_events = dut.get_last_events([], "mac")
    assert len(last_events) == 0

def test_ep_worker_func_get_last_events_mac_l2d(app):
    # ensure tw events returned for local-to-delete case 
    # mac: 
    #   ts2 (2654208/15007713/00:00:00:00:00:aa - deleted)
    #   ts1 (2654208/15007713/00:00:00:00:00:aa - vpc-344)
    events = get_test_json()
    dut = get_worker()
    last_events = dut.get_last_events(events["events"], "mac")
    print "events: %s\nlast_events: %s" % (ept_utils.pretty_print(events), 
        ept_utils.pretty_print(last_events))
    assert len(last_events) == 2
    assert last_events[0]["status"] == "deleted"
    assert last_events[1]["ifId"] == "vpc-344"

def test_ep_worker_func_get_last_events_mac_l2l(app):
    # ensure two last local events are received for local to local case
    # mac: 
    #   ts2 (2654208/15007713/00:00:00:00:00:aa - vpc-343)
    #   ts1 (2654208/15007713/00:00:00:00:00:aa - vpc-344)
    events = get_test_json()
    dut = get_worker()
    last_events = dut.get_last_events(events["events"], "mac")
    print "events: %s\nlast_events: %s" % (ept_utils.pretty_print(events), 
        ept_utils.pretty_print(last_events))
    assert len(last_events) == 2
    assert last_events[0]["ifId"] == "vpc-343"
    assert last_events[1]["ifId"] == "vpc-344"

def test_ep_worker_func_get_last_events_mac_l2r(app):
    # ensure two events are returned for local to remote case
    # mac: 
    #   ts2 (2654208/15007713/00:00:00:00:00:aa - remote)
    #   ts1 (2654208/15007713/00:00:00:00:00:aa - vpc-344)
    events = get_test_json()
    dut = get_worker()
    last_events = dut.get_last_events(events["events"], "mac")
    print "events: %s\nlast_events: %s" % (ept_utils.pretty_print(events), 
        ept_utils.pretty_print(last_events))
    assert len(last_events) == 2
    assert len(last_events[0]["remote"])>0
    assert last_events[1]["ifId"] == "vpc-344"

def test_ep_worker_func_get_last_events_mac_r2l(app):
    # ensure two events are returned for remote to local case
    # mac: 
    #   ts2 (2654208/15007713/00:00:00:00:00:aa - vpc-343)
    #   ts1 (2654208/15007713/00:00:00:00:00:aa - remote)
    events = get_test_json()
    dut = get_worker()
    last_events = dut.get_last_events(events["events"], "mac")
    print "events: %s\nlast_events: %s" % (ept_utils.pretty_print(events), 
        ept_utils.pretty_print(last_events))
    assert len(last_events) == 2
    assert last_events[0]["ifId"] == "vpc-343"
    assert len(last_events[1]["remote"])>0

def test_ep_worker_func_get_last_events_mac_l2d2l(app):
    # ensure two events are returned for local-delete-local case
    # mac: 
    #   ts3 (2654208/15007713/00:00:00:00:00:aa - vpc-343)
    #   ts2 (2654208/15007713/00:00:00:00:00:aa - deleted)
    #   ts1 (2654208/15007713/00:00:00:00:00:aa - vpc-344)
    events = get_test_json()
    dut = get_worker()
    last_events = dut.get_last_events(events["events"], "mac")
    print "events: %s\nlast_events: %s" % (ept_utils.pretty_print(events), 
        ept_utils.pretty_print(last_events))
    assert len(last_events) == 2
    assert last_events[0]["ifId"] == "vpc-343"
    assert last_events[1]["ifId"] == "vpc-344"
    
def test_ep_worker_func_get_last_events_mac_r2d2l(app):
    # ensure two events are returned for remote-delete-local case
    # mac: 
    #   ts3 (2654208/15007713/00:00:00:00:00:aa - vpc-343)
    #   ts2 (2654208/15007713/00:00:00:00:00:aa - deleted)
    #   ts1 (2654208/15007713/00:00:00:00:00:aa - remote)
    events = get_test_json()
    dut = get_worker()
    last_events = dut.get_last_events(events["events"], "mac")
    print "events: %s\nlast_events: %s" % (ept_utils.pretty_print(events), 
        ept_utils.pretty_print(last_events))
    assert len(last_events) == 2
    assert last_events[0]["ifId"] == "vpc-343"
    assert len(last_events[1]["remote"])>0

def test_ep_worker_func_get_last_events_mac_l2d2l_long_delete(app):
    # ensure two events are received for local-delete-local where delete event
    # is greater than transitory_delete threshold and therefore events are
    # delete and local
    #   ts300 (2654208/15007713/00:00:00:00:00:aa - vpc-343)
    #   ts2 (2654208/15007713/00:00:00:00:00:aa - deleted)
    #   ts1 (2654208/15007713/00:00:00:00:00:aa - vpc-344)
    events = get_test_json()
    dut = get_worker()
    last_events = dut.get_last_events(events["events"], "mac")
    print "events: %s\nlast_events: %s" % (ept_utils.pretty_print(events), 
        ept_utils.pretty_print(last_events))
    assert len(last_events) == 2
    assert last_events[0]["status"] == "created"
    assert last_events[0]["ifId"] == "vpc-343"
    assert last_events[1]["status"] == "deleted"

def test_ep_worker_func_get_last_events_mac_l2d2l_short_delete(app):
    # ensure two events are received for local-delete-local where delete event
    # is shorter than transitory_delete threshold and therefore events are
    # local to local
    #   ts201 (2654208/15007713/00:00:00:00:00:aa - vpc-343)
    #   ts200 (2654208/15007713/00:00:00:00:00:aa - deleted)
    #   ts1 (2654208/15007713/00:00:00:00:00:aa - vpc-344)
    events = get_test_json()
    dut = get_worker()
    last_events = dut.get_last_events(events["events"], "mac")
    print "events: %s\nlast_events: %s" % (ept_utils.pretty_print(events), 
        ept_utils.pretty_print(last_events))
    assert len(last_events) == 2
    assert last_events[0]["ifId"] == "vpc-343"
    assert last_events[1]["ifId"] == "vpc-344"

def test_ep_worker_func_get_last_events_ip_l2l(app):
    # ensure two events received for ip local to local case
    # where intermediate has delete of only rewrite info
    # ip:
    #   ts3 (2654208/15007713/10.1.4.101 - vpc-343,rw:0000.0000.00bb)
    #   ts2 (2654208/15007713/10.1.4.101 - vpc-343,rw:-)
    #   ts1 (2654208/15007713/10.1.4.101 - vpc-343,rw:0000.0000.00aa)
    events = get_test_json()
    dut = get_worker()
    last_events = dut.get_last_events(events["events"], "ip")
    print "events: %s\nlast_events: %s" % (ept_utils.pretty_print(events), 
        ept_utils.pretty_print(last_events))
    assert len(last_events) == 2
    assert last_events[0]["ifId"] == "vpc-343"
    assert last_events[0]["rw_mac"] == "00:00:00:00:00:bb"
    assert last_events[1]["ifId"] == "vpc-343"
    assert last_events[1]["rw_mac"] == "00:00:00:00:00:aa"

def test_ep_worker_func_get_last_events_ip_l2d2l(app):
    # ensure two events received for local-delete-local case
    # where intermediate delete is variation of status-delete along with
    # absence of rewrite info
    # ip:
    #   ts5 (2654208/15007713/10.1.4.101 - vpc-343,rw:0000.0000.00bb)
    #   ts4 (2654208/15007713/10.1.4.101 - deleted,rw:0000.0000.00bb)
    #   ts3 (2654208/15007713/10.1.4.101 - deleted,rw:-)
    #   ts2 (2654208/15007713/10.1.4.101 - vpc-343,rw:-)
    #   ts1 (2654208/15007713/10.1.4.101 - vpc-343,rw:0000.0000.00aa)
    events = get_test_json()
    dut = get_worker()
    last_events = dut.get_last_events(events["events"], "ip")
    print "events: %s\nlast_events: %s" % (ept_utils.pretty_print(events), 
        ept_utils.pretty_print(last_events))
    assert len(last_events) == 2
    assert last_events[0]["ifId"] == "vpc-343"
    assert last_events[0]["rw_mac"] == "00:00:00:00:00:bb"
    assert last_events[1]["ifId"] == "vpc-343"
    assert last_events[1]["rw_mac"] == "00:00:00:00:00:aa"

def test_ep_worker_func_ep_analyze_move_new_remote_vpc_to_vpc(app):
    # analyze move between vpc pairs
    # endpoint 10.1.5.101 move from vpc on node-103+104 to
    # vpc on node-101+102
    key = {
        "addr": "10.1.5.101",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    updates = dut.ep_analyze_move(key)
    assert "src" in updates and "dst" in updates
    assert updates["src"]["node"] == "%s" % 0x660065
    assert updates["dst"]["node"] == "%s" % 0x680067

def test_ep_worker_func_ep_analyze_move_new_local_vpc_to_vpc(app):
    # analyze move between vpcs on the same vpc domain
    key = {
        "addr": "10.1.5.102",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    updates = dut.ep_analyze_move(key)
    assert "src" in updates and "dst" in updates
    assert updates["src"]["ifId"] == "vpc-344"
    assert updates["dst"]["ifId"] == "vpc-343"

def test_ep_worker_func_ep_analyze_move_new_vpc_encap(app):
    # analyze move between encaps on same vpc
    key = {
        "addr": "10.1.5.103",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    updates = dut.ep_analyze_move(key)
    assert "src" in updates and "dst" in updates
    assert updates["src"]["encap"] == "vlan-101"
    assert updates["dst"]["encap"] == "vlan-102"

def test_ep_worker_func_ep_analyze_move_new_mac(app):
    # analyze move for ip between different rw_mac
    key = {
        "addr": "10.1.5.104",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    updates = dut.ep_analyze_move(key)
    assert "src" in updates and "dst" in updates
    assert updates["src"]["rw_mac"] == "aa:bb:cc:dd:ee:ff"
    assert updates["dst"]["rw_mac"] == "aa:bb:cc:dd:ee:00"

def test_ep_worker_func_ep_analyze_move_new_vpc_to_orphan(app):
    # analyze move between a vpc to an orphan port
    key = {
        "addr": "10.1.5.105",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    updates = dut.ep_analyze_move(key)
    assert "src" in updates and "dst" in updates
    assert updates["src"]["node"] == "%s" % 0x660065
    assert updates["dst"]["node"] == "101"

def test_ep_worker_func_ep_analyze_move_new_orphan_to_vpc(app):
    # analyze move between an orphan port to a vpc
    key = {
        "addr": "10.1.5.106",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    updates = dut.ep_analyze_move(key)
    assert "src" in updates and "dst" in updates
    assert updates["src"]["node"] == "101"
    assert updates["dst"]["node"] == "%s" % 0x660065

def test_ep_worker_func_ep_analyze_move_new_remote_orphan_to_orphan(app):
    # analyze move between to orphan ports on different nodes
    key = {
        "addr": "10.1.5.107",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    updates = dut.ep_analyze_move(key)
    assert "src" in updates and "dst" in updates
    assert updates["src"]["node"] == "101"
    assert updates["dst"]["node"] == "103"

def test_ep_worker_func_ep_analyze_move_new_local_orphan_to_orphan(app):
    # analyze move between to orphan ports on same node
    key = {
        "addr": "10.1.5.108",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    updates = dut.ep_analyze_move(key)
    assert "src" in updates and "dst" in updates
    assert updates["src"]["ifId"] == "eth1/10"
    assert updates["dst"]["ifId"] == "eth1/11"

def test_ep_worker_func_ep_analyze_move_orphan_to_delete(app):
    # analyze an orphan endpoint that is deleted (not a move)
    key = {
        "addr": "10.1.5.109",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    dut.transitory_delete_time = 0.001
    updates = dut.ep_analyze_move(key)
    assert len(updates) == 0

def test_ep_worker_func_ep_analyze_move_delete_to_orphan(app):
    # analyze an endpoint that changes from a deleted status to orphan
    # (not a move)
    key = {
        "addr": "10.1.5.110",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    dut.transitory_delete_time = 0.001
    updates = dut.ep_analyze_move(key)
    assert len(updates) == 0

def test_ep_worker_func_ep_analyze_move_old_remote_vpc_to_vpc(app):
    # analyze a move between two vpc domains with 'move' entry
    # already existing in ep_move table (not a NEW move)
    key = {
        "addr": "10.1.5.111",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    updates = dut.ep_analyze_move(key)
    assert len(updates) == 0

def test_ep_worker_func_ep_analyze_move_old_ts_remote_vpc_to_vpc(app):
    # analyze a move between two vpc domains with 'move' entry
    # already existing in ep_move table.  Although the move is different
    # from the previous move, the timestamp on the new move is less recent
    # and therefore should be ignored
    key = {
        "addr": "10.1.5.112",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    updates = dut.ep_analyze_move(key)
    assert len(updates) == 0

def test_ep_worker_func_ep_analyze_new_stale(app):
    # call ep_analyze on event to verify all functions successfully execute
    # and ensure new stale event is correctly triggered
    #
    # ip: (2654208/15007713/10.1.6.101) is on node-101 with node-103 with
    # correct bounce entry and node-104 pointing to node-103.  Event is a
    # delete on node-103 triggering a stale endpoint on node-104

    classname = "epmIpEp"
    event = get_test_json()
    pevent = ept_utils.parse_epm_event(classname, event, test_overlay_vnid,
                ts=event["_ts"])
    dut = get_worker()
    dut.trust_subscription = True
    dut.stale_double_check = False
    dut.ep_analyze(EPJob("ep_analyze", pevent, ts=event["_ts"],data=pevent)) 
    with app.app_context():
        db = app.mongo.db
        f = db.ep_stale.find_one({"fabric":test_fabric,"node":"104",
            "addr":"10.1.6.101", "vnid":"2654208"})
        assert f is not None

def test_ep_worker_func_watch_stale_new_stale_job(app):
    # ensure that new stale job sent to watch_stale is added to watched objects
    # ip: (2654208/15007713/10.1.6.102) is on node-101
    key = {
        "addr": "10.1.6.102",
        "vnid": "2654208",
        "type": "ip",
        "fabric": test_fabric,
    }
    nodes = {"101":{}, "102":{}}
    job = EPJob("watch_stale", key, ts=time.time(),data=nodes)
    dut = get_worker()
    dut.watch_event(job)
    assert len(dut.watched)==2
    matched = []
    for wkey in dut.watched:
        j = dut.watched[wkey]
        assert j.key["addr"] == key["addr"]
        assert j.key["node"] == "101" or j.key["node"] == "102"
        matched.append(j.key["node"])
    assert "101" in matched
    assert "102" in matched

def test_ep_worker_func_watch_stale_extend_execute_ts(app):
    # add duplicate stale entry where ts is identical to previous event
    # for one node and different for the second node.  Ensure that the 
    # execute_ts is only updated for the second node.
    # ip: (2654208/15007713/10.1.6.102) is on node-101
    key = {
        "addr": "10.1.6.102",
        "vnid": "2654208",
        "type": "ip",
        "fabric": test_fabric,
    }
    dut = get_worker()
    # add first job
    nodes = {"101":{"ts":1.0}, "102":{"ts":1.0}}
    job = EPJob("watch_stale", key, ts=time.time(),data=nodes)
    dut.watch_event(job)

    node_101_execute_ts = 0
    node_102_execute_ts = 0
    assert len(dut.watched)==2
    for wkey in dut.watched:
        j = dut.watched[wkey]
        if j.key["node"] == "101": node_101_execute_ts = j.execute_ts
        elif j.key["node"] == "102": node_102_execute_ts = j.execute_ts
    assert node_101_execute_ts > 0 and node_102_execute_ts > 0    

    # add second job
    nodes = {"101":{"ts":1.0}, "102":{"ts":2.0}}
    job = EPJob("watch_stale", key, ts=time.time(),data=nodes)
    dut.watch_event(job)
    assert len(dut.watched)==2
    for wkey in dut.watched:
        j = dut.watched[wkey]
        if j.key["node"] == "101":
            assert node_101_execute_ts == j.execute_ts
        elif j.key["node"] == "102":
            assert node_102_execute_ts < j.execute_ts
    

def test_ep_worker_func_watch_stale_single_stale(app):
    # ensure that single stale endpoint is watched and after transitory
    # time, stale event is added to the database
    # ip: (2654208/15007713/10.1.6.103) is on node-101
    key = {
        "addr": "10.1.6.103",
        "vnid": "2654208",
        "type": "ip",
        "fabric": test_fabric,
    }
    nodes = {"101": {}, }
    tst = 0.1
    job = EPJob("watch_stale", key, ts=time.time(),data=nodes)
    dut = get_subscriber(queue_interval=0.001,transitory_stale_time=tst,
        notify_stale_syslog=False, notify_stale_email=False,max_workers=1,
        pworker_disable=True)
    try:
        dut.start_workers()
        dut.wworker["txQ"].put(job)
        time.sleep(tst*5)
        # ensure stale event added to database
        with app.app_context():
            db = app.mongo.db
            f = db.ep_stale.find_one(key)
            assert f is not None
            assert f["node"] == "101"
    finally:
        dut.stop_workers()

def test_ep_worker_func_watch_stale_double_stale(app):
    # ensure that transitory time is extended when duplicate stale event
    # is sent to watch_stale. After new transitory time is expired, ensure
    # stale event is added to the database
    # ip: (2654208/15007713/10.1.6.104) is on node-101
    key = {
        "addr": "10.1.6.104",
        "vnid": "2654208",
        "type": "ip",
        "fabric": test_fabric,
    }
    nodes = {"101": {}, }
    tst = 0.1
    job = EPJob("watch_stale", key, ts=time.time(),data=nodes)
    dut = get_subscriber(queue_interval=0.001,transitory_stale_time=tst,
        notify_stale_syslog=False, notify_stale_email=False,max_workers=1,
        pworker_disable=True)
    try:
        dut.start_workers()
        dut.wworker["txQ"].put(job)
        time.sleep(tst/2.0)
        dut.wworker["txQ"].put(job)
        time.sleep(tst/2.0)
        # ensure stale event added to database
        with app.app_context():
            db = app.mongo.db
            f = db.ep_stale.find_one(key)
            # new job extended transitory time, so no update in database yet
            assert f is None
            time.sleep(tst*5.0)
            # now, after waiting full transitory time, should see an update
            f = db.ep_stale.find_one(key)
            assert f is not None
            assert f["node"] == "101"
    finally:
        dut.stop_workers()

def test_ep_worker_func_watch_stale_cleared(app):
    # watch is called for a stale endpoint, before the transitory time has
    # experied, is_stale is cleared for the endpoint.  Ensure that NO new
    # event is added to stale_ep database
    # ip: (2654208/15007713/10.1.6.105) is no longer stale on node-101
    key = {
        "addr": "10.1.6.105",
        "vnid": "2654208",
        "type": "ip",
        "fabric": test_fabric,
    }
    nodes = {"101": {}, }
    tst = 0.1
    job = EPJob("watch_stale", key, ts=time.time(),data=nodes)
    dut = get_subscriber(queue_interval=0.001,transitory_stale_time=tst,
        notify_stale_syslog=False, notify_stale_email=False,max_workers=1,
        pworker_disable=True)
    try:
        dut.start_workers()
        dut.wworker["txQ"].put(job)
        # ensure stale event added to database
        with app.app_context():
            db = app.mongo.db
            db.ep_history.update_one(key, {"$set":{"is_stale":False}})
            time.sleep(tst*5)
            f = db.ep_stale.find_one(key)
            assert f is None
    finally:
        dut.stop_workers()

def test_ep_worker_func_watch_stale_multiple_nodes(app):
    # for the same stale endpoint on multiple nodes, ensure that after
    # transitory time, a stale event is added for all nodes
    # ip: (2654208/15007713/10.1.6.106) is on node-101 through 104
    key = {
        "addr": "10.1.6.106",
        "vnid": "2654208",
        "type": "ip",
        "fabric": test_fabric,
    }
    nodes = {"101": {}, "102":{}, "103":{}, "104":{}}
    tst = 0.1
    job = EPJob("watch_stale", key, ts=time.time(),data=nodes)
    dut = get_subscriber(queue_interval=0.001,transitory_stale_time=tst,
        notify_stale_syslog=False, notify_stale_email=False,max_workers=1,
        pworker_disable=True)
    try:
        dut.start_workers()
        dut.wworker["txQ"].put(job)
        time.sleep(tst*5)
        # ensure stale event added to database
        with app.app_context():
            db = app.mongo.db
            matched = []
            for f in db.ep_stale.find(key):
                assert f["node"] == "101" or f["node"]=="102" or \
                    f["node"] == "103" or f["node"] == "104" 
                matched.append(f["node"])
            assert "101" in matched
            assert "102" in matched
            assert "103" in matched
            assert "104" in matched
    finally:
        dut.stop_workers()

def test_ep_worker_complete_execute(app):
    # starting at ep_subscription subscribe_to_objects, generate a 
    # stale event for node-101 (pointing to node-104 where node-104 has no
    # events and is therefore stale).  Ensure that worker analysis event
    # and enqueues it onto watch queue, and finally watch queue picks up 
    # event after transitory_stale_time and adds to database
    # ip: (2654208/15007713/10.1.6.107) XR on node-101 only
    key = {
        "addr": "10.1.6.107",
        "vnid": "2654208",
        "type": "ip",
        "fabric": test_fabric,
    }
    events = [
        "tests/testdata/ept/test_ep_worker_complete_execute.json"
    ]
    tst = 0.01
    dut = get_subscriber(queue_interval=0.001,transitory_stale_time=tst,
        transitory_xr_stale_time=tst,
        notify_stale_syslog=False, notify_stale_email=False,max_workers=1,
        event_file=events, monitor_disable=True, controller_interval=0.001)
    try:
        dut.subscribe_to_objects()
        # wait 3x tst and ensure watcher has marked endpoint as stale
        time.sleep(tst*3)
        with app.app_context():
            db = app.mongo.db
            f = db.ep_stale.find_one(key)
            assert f is not None
            assert f["node"] == "101"
    finally:
        dut.stop_workers()

def test_ep_worker_func_watch_event_auto_clear(app):
    # enqueue a watch_offsubnet job with expired execute_ts and 
    # auto_clear_offsubnet set to true and ensure clear command is sent to
    # simulator and endpoint is added to ep_offsubnet table
    # ip: (2654208/15007713/10.1.6.108)
    connection_sim.clear()
    connection_sim.default = ""
    key = {
        "addr": "10.1.6.108",
        "vnid": "2654208",
        "type": "ip",
        "fabric": test_fabric,
        "node":"101"
    }
    dut = get_worker()
    dut.auto_clear_offsubnet = True
    # add first job
    nodes = {"101":{"ts":1.0}}
    job = EPJob("watch_offsubnet", key, ts=time.time(),data=nodes,
                execute_ts=1.0)
    dut.watch_event(job)


def test_utils_func_get_controller_version(app):
    # verify get_controller_version returns all controller nodes and 
    # corresponding versions.  test file has 3 nodes (1-3) running version
    # 2.2(1n)
    sim.clear()
    filename = "tests/testdata/ept/utils_func_get_controller_version.json"
    sim.add_event_file(filename)
    sim.start()
    session = ept_utils.get_apic_session(test_fabric)
    ctrls = ept_utils.get_controller_version(session)
    assert len(ctrls) == 3
    nodes = []
    for c in ctrls:
        assert c["version"] == "2.2(1n)"
        nodes.append(int(c["node"]))
    assert 1 in nodes
    assert 2 in nodes
    assert 3 in nodes

def test_utils_func_get_ipv4_prefix(app):
    # test several ipv4 addresses and ensure correct (addr,mask) are returned
    (addr, mask) = ept_utils.get_ipv4_prefix("10.1.1.1/24")
    assert addr == 0x0a010100 and mask == 0xffffff00
    (addr, mask) = ept_utils.get_ipv4_prefix("10.1.1.1")
    assert addr == 0x0a010101 and mask == 0xffffffff
    (addr, mask) = ept_utils.get_ipv4_prefix("10.1.1.1/0")
    assert addr == 0x00000000 and mask == 0x00000000
    (addr, mask) = ept_utils.get_ipv4_prefix("10.1.1.1/1")
    assert addr == 0x00000000 and mask == 0x80000000
    (addr, mask) = ept_utils.get_ipv4_prefix("128.1.1.1/1")
    assert addr == 0x80000000 and mask == 0x80000000
    (addr, mask) = ept_utils.get_ipv4_prefix("192.168.27.88/27")
    assert addr == 0xc0a81b40 and mask == 0xffffffe0
    (addr, mask) = ept_utils.get_ipv4_prefix("-1.23.1")
    assert addr is None and mask is None
    (addr, mask) = ept_utils.get_ipv4_prefix("256.1.1.1/23")
    assert addr is None and mask is None
    (addr, mask) = ept_utils.get_ipv4_prefix("255.1.1.1/33")
    assert addr is None and mask is None
    (addr, mask) = ept_utils.get_ipv4_prefix("255.1.1.1/32")
    assert addr == 0xff010101 and mask == 0xffffffff

def test_utils_func_get_ipv6_prefix(app):
    # test several ipv6 addresses and ensure correct (addr,mask) are returned
    (addr, mask) = ept_utils.get_ipv6_prefix("::")
    assert addr == 0x0 and mask == 0xffffffffffffffffffffffffffffffff
    (addr, mask) = ept_utils.get_ipv6_prefix("::1/64")
    assert  addr == 0x00000000000000000000000000000000 \
        and mask == 0xffffffffffffffff0000000000000000
    (addr, mask) = ept_utils.get_ipv6_prefix("::1/128")
    assert  addr == 0x00000000000000000000000000000001 \
        and mask == 0xffffffffffffffffffffffffffffffff
    (addr, mask) = ept_utils.get_ipv6_prefix("::1")
    assert  addr == 0x00000000000000000000000000000001 \
        and mask == 0xffffffffffffffffffffffffffffffff
    (addr, mask) = ept_utils.get_ipv6_prefix("fe80::9a5a:ebff:fecb:a095")
    assert  addr == 0xfe800000000000009a5aebfffecba095 \
        and mask == 0xffffffffffffffffffffffffffffffff
    (addr, mask) = ept_utils.get_ipv6_prefix("fe80::9a5a:ebff:fecb:a095/64")
    assert  addr == 0xfe800000000000000000000000000000 \
        and mask == 0xffffffffffffffff0000000000000000
    (addr, mask) = ept_utils.get_ipv6_prefix("2001::1")
    assert  addr == 0x20010000000000000000000000000001 \
        and mask == 0xffffffffffffffffffffffffffffffff
    (addr, mask) = ept_utils.get_ipv6_prefix("2001::1/64")
    assert  addr == 0x20010000000000000000000000000000 \
        and mask == 0xffffffffffffffff0000000000000000
    (addr, mask) = ept_utils.get_ipv6_prefix("::2001")
    assert  addr == 0x00000000000000000000000000002001 \
        and mask == 0xffffffffffffffffffffffffffffffff
    (addr, mask) = ept_utils.get_ipv6_prefix("::2001:2002")
    assert  addr == 0x00000000000000000000000020012002 \
        and mask == 0xffffffffffffffffffffffffffffffff
    (addr, mask) = ept_utils.get_ipv6_prefix("2001:2002::")
    assert  addr == 0x20012002000000000000000000000000 \
        and mask == 0xffffffffffffffffffffffffffffffff
    (addr, mask) = ept_utils.get_ipv6_prefix("2001:2002::abcd:1234")
    assert  addr == 0x200120020000000000000000abcd1234 \
        and mask == 0xffffffffffffffffffffffffffffffff
    (addr, mask) = ept_utils.get_ipv6_prefix(
                    "2001:1678:9abc:def0::def0/122")
    assert  addr == 0x200116789abcdef0000000000000dec0 \
        and mask == 0xffffffffffffffffffffffffffffffc0
    (addr, mask) = ept_utils.get_ipv6_prefix("2001::12:1:1:102")
    assert  addr == 0x20010000000000000012000100010102 \
        and mask == 0xffffffffffffffffffffffffffffffff

def test_func_set_fabric_warning(app):
    # set a fabric warning and read to ensure it was correctly set
    fab_warning = "arbitrary warning..."
    assert ept_utils.set_fabric_warning(test_fabric, fab_warning)
    with app.app_context():
        db = app.mongo.db
        f = db.ep_settings.find_one({"fabric":test_fabric})
        assert f["fabric_warning"] == fab_warning
        # clear the warning
        assert ept_utils.clear_fabric_warning(test_fabric)
        f = db.ep_settings.find_one({"fabric":test_fabric})
        assert f["fabric_warning"] == ""
    
def test_ep_subscriber_func_apic_version_trust_subscription(app):
    # trusted versions of code are >= 2.2(1a).  Verify correct trust
    # state is returned based on various versions of code
    should_pass = ["2.2(1a)", "2.2(1n)", "2.2(1.73)", "2.2(2a)", "2.2(3b)",
                    "2.3(0.21)", "2.3(1a)", "3.0(0.73)", "3.0(1a)", "3.1(1b)"]
    should_fail = ["1.0(1a)", "1.1(0.193)", "1.2(3m)", "2.1(1h)", "2.1(2e)"]
    invalid_version = ["1.1.12", None, "1.2(3a23)", "2.2(5a)1"]
    for v in should_pass:
        assert ep_subscriber.apic_version_trust_subscription(v) is True
    for v in should_fail:
        assert ep_subscriber.apic_version_trust_subscription(v) is False
    for v in invalid_version:
        assert ep_subscriber.apic_version_trust_subscription(v) is None


def test_ep_priority_worker_func_handle_event_fabricNode_active(app):
    # verify ep_priority_worker puts job on broadcast queue with node-101
    # and status of 'active'
    event = get_test_json()
    job = EPJob("handle_event", {}, data={"classname":"fabricNode",
        "event":event})
    dut = get_priority_worker()
    dut.handle_event(job)
    assert dut.txQ.qsize() > 0
    qjob = dut.txQ.get_nowait()
    assert qjob.action == "requeue"
    assert len(qjob.data["jobs"]) == 1
    watch_job = qjob.data["jobs"][0]
    assert watch_job.action == "watch_node"
    assert watch_job.data["node"] == "101"
    assert watch_job.data["status"] == "active"

def test_ep_priority_worker_func_handle_event_fabricNode_inactive(app):
    # verify ep_priority_worker puts job on broadcast queue with node-101
    # and status of 'inactive'
    event = get_test_json()
    job = EPJob("handle_event", {}, data={"classname":"fabricNode",
        "event":event})
    dut = get_priority_worker()
    dut.handle_event(job)
    assert dut.txQ.qsize() > 0
    qjob = dut.txQ.get_nowait()
    assert qjob.action == "requeue"
    assert len(qjob.data["jobs"]) == 1
    watch_job = qjob.data["jobs"][0]
    assert watch_job.action == "watch_node"
    assert watch_job.data["node"] == "101"
    assert watch_job.data["status"] == "inactive"

def test_ep_priority_worker_func_handle_event_fabricNode_spine(app):
    # verify no event is triggered when non-leaf (spine/controller) goes
    # active or inactive
    event = get_test_json()
    job = EPJob("handle_event", {}, data={"classname":"fabricNode",
        "event":event})
    dut = get_priority_worker()
    dut.handle_event(job)
    assert dut.txQ.qsize() == 0

def test_ep_subscriber_func_extend_hello(app):
    # extend single worker hello time and verify that while no hellos are
    # sent during interval, subscriber does not trigger restart
    dut = get_subscriber(queue_interval=0.001, controller_interval=0.001,
        max_workers=1, monitor_disable=True, worker_hello=0.003)
    dut.wworker_disable = True
    dut.pworker_disable = True
    try:
        # start single worker and send a hello - refresh to set initial ts
        dut.start_workers()
        dut.workers[0]["prQ"].put(EPJob("hello",{}))
        time.sleep(dut.queue_interval*10)
        dut.refresh_workers()
        # sleep for 5x hello and ensure check_worker returns false(not alive)
        time.sleep(dut.worker_hello*5)
        assert dut.check_worker_hello() is False
        # extend worker hello and re-check should should be true
        ejob = EPJob("extend_hello", {}, data={"time":0.1})
        dut.extend_hello(ejob, dut.workers[0])
        assert dut.check_worker_hello() is True
    finally:
        dut.stop_workers()

def test_ep_subscriber_func_enqueue_job_for_watcher(app):
    # ensure enqueue_job with type watch_ is sent to watcher queue
    
    dut = get_subscriber(queue_interval=0.001, controller_interval=0.001,
        max_workers=1, monitor_disable=True, worker_hello=0.003)
    dut.pworker_disable = True
    dut.workers[0] = {
        "wid": 0, "txQ": simulator.mQueue(), "rxQ": simulator.mQueue(),
        "process": None, "last_hello":0
    }
    dut.wworker = {
        "wid": 0, "txQ": simulator.mQueue(), "rxQ": simulator.mQueue(),
        "process": None, "last_hello":0
    }
    try:
        job = EPJob("watch_hello", {})
        dut.enqueue_job(job)
        assert dut.wworker["txQ"].qsize() == 1
    finally:
        dut.stop_workers()
    pass

def test_ep_subscriber_func_requeue_job(app):
    # execute requeue_job with multiple jobs and ensure each job is enqueued
    # on a worker.  Watch job is enqueued on watch worker
    dut = get_subscriber(queue_interval=0.001, controller_interval=0.001,
        max_workers=1, monitor_disable=True, worker_hello=0.003)
    dut.pworker_disable = True
    dut.workers[0] = {
        "wid": 0, "txQ": simulator.mQueue(), "rxQ": simulator.mQueue(),
        "process": None, "last_hello":0
    }
    dut.wworker = {
        "wid": 0, "txQ": simulator.mQueue(), "rxQ": simulator.mQueue(),
        "process": None, "last_hello":0
    }
    try:
        job = EPJob("requeue", {}, data={"jobs":[]})
        job.data["jobs"].append(EPJob("watch_hello", {}))
        for x in xrange(0, 5):
            job.data["jobs"].append(EPJob("worker_hello", {}))
        dut.requeues.append(job)
        dut.requeue_jobs()
        assert dut.wworker["txQ"].qsize() == 1
        assert dut.workers[0]["txQ"].qsize() == 5
    finally:
        dut.stop_workers()
    pass

def test_ep_worker_func_watch_node_inactive_event(app):
    # send inactive node event to watch_node and ensure delete events are created
    # node-201 should see deletes for:
    #   (1) IP XR 10.1.7.101, 
    #   (1) IP XR 10.1.7.103
    #   (2) IP Local 10.1.7.104 + epmRxMacEpToIpEpAtt
    #   (1) MAC Local 00:00:00:00:00:01
    #   (1) MAC XR 00:00:00:00:00:03
    # endpoints on node-201 that should not be deleted
    #   XR 10.1.7.102, local 10.1.7.105,
    #   local 00:00:00:00:00:02, XR 00:00:00:00:00:04
    dut = get_worker()
    dut.watch_node(EPJob("watch_node", {}, data={
        "node": "201", "pod": "1", "status": "inactive"
    }))
    n = {}
    while dut.txQ.qsize()>0: 
        j = dut.txQ.get()   
        if j.action != "requeue": continue
        for sj in j.data["jobs"]:
            n["%s-%s" % (sj.data["classname"], sj.key["addr"])] = sj
            assert sj.data["status"] == "deleted"
    assert len(n) == 6
    assert "epmIpEp-10.1.7.101" in n
    assert "epmIpEp-10.1.7.103" in n
    assert "epmIpEp-10.1.7.104" in n
    assert "epmRsMacEpToIpEpAtt-10.1.7.104" in n
    assert "epmMacEp-00:00:00:00:00:01" in n
    assert "epmMacEp-00:00:00:00:00:03" in n

def test_ep_worker_func_watch_node_active_event(app):
    # send active node event to watch_node and ensure create events are created
    # for all endpoints returned from query
    # (1) local mac 0000.0000.0005
    # (1) remote mac 0000.0000.0006
    # (1) local IP 10.1.7.106
    # (1) local rewrite for 10.1.7.106 with mac 0000.0000.0005
    # (1) remote IP 10.1.7.107

    e = "tests/testdata/ept/test_ep_worker_func_watch_node_active_event.json"
    dut = get_worker(e)
    dut.watch_node(EPJob("watch_node", {}, data={
        "node": "201", "pod": "1", "status": "active"
    }))
    n = {}
    while dut.txQ.qsize()>0: 
        j = dut.txQ.get()   
        if j.action != "requeue": continue
        for sj in j.data["jobs"]:
            n["%s-%s" % (sj.data["classname"], sj.key["addr"])] = sj
            assert sj.data["status"] == "created"
    assert len(n) == 5
    assert "epmMacEp-00:00:00:00:00:05" in n
    assert "epmMacEp-00:00:00:00:00:06" in n
    assert "epmIpEp-10.1.7.106" in n
    assert "epmIpEp-10.1.7.107" in n
    assert "epmRsMacEpToIpEpAtt-10.1.7.106" in n

def test_ep_worker_func_clear_node_endpoint_mac(app):
    # verify clear command is correctly executed to clear mac ep
    connection_sim.clear()
    connection_sim.default = ""
    key = {
        "type":"mac",
        "vlan": "10",
        "vrf": "ag:v1",
        "addr": "00:00:30:02:01:02"
    }
    kwargs = {
        "rQ": simulator.mQueue(),
        "hostname": "192.168.5.101",
        "username": "admin",
        "password": "ins3965!",
        "key": key
    }
    clear_node_endpoint(**kwargs)
    rQ = kwargs["rQ"]
    assert rQ.qsize() == 1
    job = rQ.get_nowait()
    assert job.data["success"] is True

def test_ep_worker_func_clear_node_endpoint_ip(app):
    # verify clear command is correctly executed to clear ip ep
    connection_sim.clear()
    connection_sim.default = ""
    key = {
        "type":"ip",
        "vlan": "",
        "vrf": "ag:v1",
        "addr": "10.1.1.101"
    }
    kwargs = {
        "rQ": simulator.mQueue(),
        "hostname": "192.168.5.101",
        "username": "admin",
        "password": "ins3965!",
        "key": key
    }
    clear_node_endpoint(**kwargs)
    rQ = kwargs["rQ"]
    assert rQ.qsize() == 1
    job = rQ.get_nowait()
    assert job.data["success"] is True

def test_ep_worker_func_clear_node_endpoint_exec_error(app):
    # if clear command returns exec_error, ensure that is captured 
    # in the details and not recorded as a success
    connection_sim.clear()
    connection_sim.add_cmds(get_test_json())
    key = {
        "type":"ip",
        "vlan": "",
        "vrf": "ag:v1",
        "addr": "10.1.1.101"
    }
    kwargs = {
        "rQ": simulator.mQueue(),
        "hostname": "192.168.5.101",
        "username": "admin",
        "password": "ins3965!",
        "key": key
    }
    clear_node_endpoint(**kwargs)
    rQ = kwargs["rQ"]
    assert rQ.qsize() == 1
    job = rQ.get_nowait()
    assert job.data["success"] is False
    assert "exec error" in job.data["details"]

def test_ep_worker_func_clear_node_endpoint_proxy(app):
    # ensure proxy function works for clear command for inband-tep
    connection_sim.clear()
    connection_sim.default = ""
    key = {
        "type":"ip",
        "vlan": "",
        "vrf": "ag:v1",
        "addr": "10.1.1.101"
    }
    kwargs = {
        "rQ": simulator.mQueue(),
        "proxy_hostname": "192.168.5.11",
        "hostname": "10.0.88.95",
        "username": "admin",
        "password": "ins3965!",
        "key": key
    }
    clear_node_endpoint(**kwargs)
    rQ = kwargs["rQ"]
    assert rQ.qsize() == 1
    job = rQ.get_nowait()
    assert job.data["success"] is True

def test_ep_worker_func_clear_node_endpoint_https_proxy(app):
    # ensure proxy function works for clear command for inband-tep
    # WHEN passed an https url instead of full hostname
    connection_sim.clear()
    connection_sim.default = ""
    key = {
        "type":"ip",
        "vlan": "",
        "vrf": "ag:v1",
        "addr": "10.1.1.101"
    }
    kwargs = {
        "rQ": simulator.mQueue(),
        "proxy_hostname": "https://192.168.5.11/more_stuff",
        "hostname": "10.0.88.95",
        "username": "admin",
        "password": "ins3965!",
        "key": key
    }
    clear_node_endpoint(**kwargs)
    rQ = kwargs["rQ"]
    assert rQ.qsize() == 1
    job = rQ.get_nowait()
    assert job.data["success"] is True

def test_ep_worker_func_clear_fabric_endpoint_spine(app):
    # ensure check is skipped when clear command executed on spine node
    connection_sim.clear()
    connection_sim.default = ""
    onodes = ["201"]
    key = {
        "addr": "10.1.1.101",
        "vnid": "2654208",
        "type": "ip"
    }
    with app.app_context():
        db = app.mongo.db
        nodes = clear_fabric_endpoint(db, test_fabric, key, onodes)
        assert "201" in nodes
        assert nodes["201"]["ret"]["success"] is False
        assert "role:spine" in nodes["201"]["ret"]["details"] 
    
def test_ep_worker_func_clear_fabric_endpoint_ip_single(app):
    # clear ip endpoint for single node and ensure return job is success
    connection_sim.clear()
    connection_sim.default = ""
    onodes = ["101"]
    key = {
        "addr": "10.1.1.101",
        "vnid": "2654208",
        "type": "ip"
    }
    with app.app_context():
        db = app.mongo.db
        nodes = clear_fabric_endpoint(db, test_fabric, key, onodes)
        assert "101" in nodes
        assert nodes["101"]["ret"]["success"] is True

def test_ep_worker_func_clear_fabric_endpoint_ip_batch_small(app):
    # using bulk size of 1, ensure clear across multiple nodes is successful
    connection_sim.clear()
    connection_sim.default = ""
    onodes = ["101", "102", "103", "104"]
    key = {
        "addr": "10.1.1.101",
        "vnid": "2654208",
        "type": "ip"
    }
    with app.app_context():
        db = app.mongo.db
        nodes = clear_fabric_endpoint(db, test_fabric,key,onodes,batch_size=1)
        assert len(nodes) == len(onodes)
        for n in onodes:
            assert n in nodes
            assert nodes[n]["ret"]["success"] is True

def test_ep_worker_func_clear_fabric_endpoint_ip_batch_large(app):
    # using bulk size of 16, ensure clear across multiple nodes is successful
    connection_sim.clear()
    connection_sim.default = ""
    onodes = ["101", "102", "103", "104"]
    key = {
        "addr": "10.1.1.101",
        "vnid": "2654208",
        "type": "ip"
    }
    with app.app_context():
        db = app.mongo.db
        nodes = clear_fabric_endpoint(db, test_fabric,key,onodes,batch_size=16)
        assert len(nodes) == len(onodes)
        for n in onodes:
            assert n in nodes
            assert nodes[n]["ret"]["success"] is True

def test_ep_worker_func_clear_fabric_endpoint_ip_timeout(app):
    # setting timeout to short value, ensure processes are killed
    connection_sim.clear()
    connection_sim.default = ""
    onodes = ["101"]
    key = {
        "addr": "10.1.1.101",
        "vnid": "2654208",
        "type": "ip"
    }
    with app.app_context():
        db = app.mongo.db
        nodes = clear_fabric_endpoint(db, test_fabric, key, onodes,timeout=0)
        assert "101" in nodes
        assert nodes["101"]["ret"]["success"] is False
        assert "timeout" in nodes["101"]["ret"]["details"]

def test_ep_worker_func_clear_fabric_endpoint_mac(app):
    # clear mac endpoint for multiple nodes and ensure return job success
    # event file forces following PI vlans for each node:
    #   node-101:vlan-3, node-102:vlan-4, node-103:vlan-7, node-104:vlan-2
    connection_sim.clear()
    connection_sim.default = ""
    sim.clear()
    event_file = "tests/testdata/ept/"
    event_file+= "ep_worker_func_clear_fabric_endpoint_mac.json"
    sim.add_event_file(event_file)
    sim.start()
    onodes = ["101", "102", "103", "104"]
    key = {
        "addr": "00:00:30:01:01:01",
        "vnid": "15007713",
        "type": "mac"
    }
    with app.app_context():
        db = app.mongo.db
        nodes = clear_fabric_endpoint(db, test_fabric, key, onodes)
        assert len(nodes) == 4
        for n in onodes:
            assert n in nodes
            assert nodes[n]["ret"]["success"] is True
        assert nodes["101"]["vlan"] == "3"
        assert nodes["102"]["vlan"] == "4"
        assert nodes["103"]["vlan"] == "7"
        assert nodes["104"]["vlan"] == "2"

def test_ep_worker_func_clear_fabric_endpoint_missing_mac(app):
    # clear mac endpoint for multiple nodes where each node has a specific error
    # node-101: epmMacEp not present
    # node-102: vlanCktEp not found
    # node-103: valid
    # node-105: invalid node
    connection_sim.clear()
    connection_sim.default = ""
    sim.clear()
    event_file = "tests/testdata/ept/"
    event_file+= "ep_worker_func_clear_fabric_endpoint_missing_mac.json"
    sim.add_event_file(event_file)
    sim.start()
    onodes = ["101", "102", "103", "105"]
    key = {
        "addr": "00:00:30:01:01:01",
        "vnid": "15007713",
        "type": "mac"
    }
    with app.app_context():
        db = app.mongo.db
        nodes = clear_fabric_endpoint(db, test_fabric, key, onodes)
        assert len(nodes) == 4
        for n in onodes: assert n in nodes
        assert nodes["101"]["ret"]["success"] is False
        assert "not currently learned" in nodes["101"]["ret"]["details"]
        assert nodes["102"]["ret"]["success"] is False
        assert "failed to map vlan" in nodes["102"]["ret"]["details"]
        assert nodes["103"]["ret"]["success"] is True
        assert nodes["105"]["ret"]["success"] is False
        assert "Node not found" in nodes["105"]["ret"]["details"]

def test_ep_worker_func_ep_analyze_offsubnet_all(app):
    # single node test (all events on node-101, XR learn)
    # ensure offsubnet is detected correctly for ipv4/ipv6 for the following 
    #   - bd exists in ep_subnets with one or more subnets that do not
    #       match endpoint's IP (epg-e1, pcTag 16500)
    # ensure offsubnet is NOT detected for ipv4/ipv6 under for the following:
    #   - pcTag 'any' (pcTag 'any')
    #   - unable to map epg pcTag to a bd_vnid  (epg-e3, pcTag 16502)
    #   - bd does not exist in ep_subnets (epg-e4, pcTag 16503)
    #   - ep_subnets contains the corresponding subnet (epg-e1, pcTag 16500)
    #       
    # dependent db entries:
    # "vnid": "3000000", uni/tn-offsubnet/ctx-v1
    # uni/tn-offsubnet/BD-bd1 (15000000)
    #       - subnets   12.1.1.1/24, 12.2.1.1/24, 2001::12:1:1:1/120, 
    #                   2001::12:2:1:1/120
    # uni/tn-offsubnets/BD-bd2 (15000001)
    #       - subnets   (present but no subnets)
    # uni/tn-offsubnets/BD-bd3 (15000002)
    #       - subnets   (not present in ep_subnets table)  
    # uni/tn-offsubnet/ap-app/epg-e1 (pcTag 16500, bd_vnid 15000000)
    # uni/tn-offsubnet/ap-app/epg-e2 (pcTag 16501, bd_vnid 15000001)
    # uni/tn-offsubnet/ap-app/epg-e3 (pcTag 16502, bd_vnid 15000002)
    # uni/tn-offsubnet/ap-app/epg-e4 (pcTag 16503, bd_vnid <empty>)

    key = {"fabric":test_fabric, "vnid":"3000000","type":"ip","addr":""}
    dut = get_worker()
    dut.trust_subscription = True
    dut.stale_double_check = True

    print "ipv4 ep is offsubnet 13.1.1.101\n%s" % ("*"*50)
    key["addr"] = "13.1.1.101"
    updates = dut.ep_analyze_offsubnet(key)
    assert len(updates) == 1
    assert "101" in updates
    assert updates["101"]["addr"] == "13.1.1.101"

    print "ipv6 ep is offsubnet 2001::13:1:1:101\n%s" % ("*"*50)
    key["addr"] = "2001::13:1:1:101"
    updates = dut.ep_analyze_offsubnet(key)
    assert len(updates) == 1
    assert "101" in updates
    assert updates["101"]["addr"] == "2001::13:1:1:101"

    print "ipv4 bd does not exist case 12.1.1.101\n%s" % ("*"*50)
    key["addr"] = "12.1.1.101"
    updates = dut.ep_analyze_offsubnet(key)
    assert len(updates) == 0

    print "ipv6 bd does not exist case 2001::12.1.1.101\n%s" % ("*"*50)
    key["addr"] = "2001:12.1.1.101"
    updates = dut.ep_analyze_offsubnet(key)
    assert len(updates) == 0

    print "ipv4 ep pcTag 'any' 13.1.1.102\n%s" % ("*"*50)
    key["addr"] = "13.1.1.102"
    updates = dut.ep_analyze_offsubnet(key)
    assert len(updates) == 0

    print "ipv6 ep pcTag 'any' 2001::13:1:1:102\n%s" % ("*"*50)
    key["addr"] = "2001::13:1:1:102"
    updates = dut.ep_analyze_offsubnet(key)
    assert len(updates) == 0

    print "ipv4 ep no bd_vnid 13.1.1.103\n%s" % ("*"*50)
    key["addr"] = "13.1.1.103"
    updates = dut.ep_analyze_offsubnet(key)
    assert len(updates) == 0

    print "ipv6 ep no bd_vnid 2001::13:1:1:103\n%s" % ("*"*50)
    key["addr"] = "2001::13:1:1:103"
    updates = dut.ep_analyze_offsubnet(key)
    assert len(updates) == 0

    print "ipv4 ep is on correct subnet 12.1.1.102\n%s" % ("*"*50)
    key["addr"] = "12.1.1.102"
    updates = dut.ep_analyze_offsubnet(key)
    assert len(updates) == 0

    print "ipv6 ep is on correct subnet 2001::12:1:1:102\n%s" % ("*"*50)
    key["addr"] = "2001::12:1:1:102"
    updates = dut.ep_analyze_offsubnet(key)
    assert len(updates) == 0
    updates = dut.ep_analyze_offsubnet(key)

    
        












##############################################################################
# Manually executed/verified tests 
##############################################################################
manually_executing = False

def test_bulk_insert_time(app):
    # test time for bulk inserts
    if not manually_executing: return 

    dut = get_worker()
    event = {"addr":"10.1.1.101", "ts":18443934224.34, "type":"ip", 
            "node":"101", "vnid":"2654208"}
    entry = { "dn": "", "pcTag":"", "flags":"", "ifId":"", 
        "encap":"", "rw_bd":"", "rw_mac":"", "remote":"", 
        "vrf":"", "bd":"",
        "status": "deleted", "vnid_name":"", "epg_name":"",
        "addr": event["addr"], "ts": event["ts"]
    }
    db_key = {
        "fabric": test_fabric, "type": event["type"], "addr":entry["addr"],
        "vnid": event["vnid"], "node": event["node"]
    }
    max_ep_events = 64
    with app.app_context():
        db = app.mongo.db
        ept_utils.update_use_bulk = True
        start = time.time()
        for x in xrange(0,30000):
            if not ept_utils.push_event(
                db = db, rotate = max_ep_events, key=db_key,
                table = "ep_history", event=entry):
                print("failed to add update to db(%s: %s)" % (
                        db_key, entry))

        r = ept_utils.bulk_update("ep_history", 
                ept_utils.update_bulk_entries, app=app)
        print r
        print("\n\nentries:%s, total time: %f" % (x+1,time.time() - start))

def test_ept_ep_notify_stale_email(app):
    # send email for stale endpoint
    if not manually_executing: return 
    key = {
        "addr": "10.1.4.101",
        "vnid": "2654208",
        "type": "ip",
        "node": "102"
    }
    stale = {
        "remote": "101",
        "expected_remote": "%s" % 0x680067,
        "vnid_name": "uni/tn-ag/ctx-v1"
    }
    dut = get_worker()
    dut.notify_email = "agossett@cisco.com"
    dut.notify_stale_email = True
    dut.ep_notify_stale(key, stale)

def test_ept_ep_notify_stale_syslog(app):
    # send syslog for stale endpoint
    if not manually_executing: return 
    key = {
        "addr": "10.1.4.101",
        "vnid": "2654208",
        "type": "ip",
        "node": "102"
    }
    stale = {
        "remote": "101",
        "expected_remote": "%s" % 0x680067,
        "vnid_name": "uni/tn-ag/ctx-v1"
    }
    dut = get_worker()
    dut.notify_syslog = "192.168.1.72"
    dut.notify_stale_syslog = True
    dut.ep_notify_stale(key, stale)

def test_ept_ep_notify_move_email(app):
    # send email for endpoint move
    if not manually_executing: return 
    key = {
        "addr": "10.1.4.101",
        "vnid": "2654208",
        "type": "ip",
    }
    move = {
        "src": {
            "node": "%s" % 0x680067,
            "ifId": "vpc-384", "encap": "vlan-101",
            "pcTag": "48934", "rw_bd": "15728629",
            "rw_mac": "aa:bb:cc:dd:ee:ff",
            "epg_name":"uni/tn-ag/ap-app/epg-e1",
            "vnid_name": "uni/tn-ag/ctx-v1"
        }, "dst": {
            "node": "%s" % 0x660065,
            "ifId": "vpc-381", "encap": "vlan-101",
            "pcTag": "48934", "rw_bd": "15728629",
            "rw_mac": "aa:bb:cc:dd:ee:ff",
            "epg_name":"uni/tn-ag/ap-app/epg-e1",
            "vnid_name": "uni/tn-ag/ctx-v1"
        }
    }
    dut = get_worker()
    dut.notify_email = "agossett@cisco.com"
    dut.notify_move_email = True
    dut.ep_notify_move(key, move)

def test_ept_ep_notify_move_syslog(app):
    # send syslog for endpoint move
    if not manually_executing: return 
    key = {
        "addr": "10.1.4.101",
        "vnid": "2654208",
        "type": "ip",
    }
    move = {
        "src": {
            "node": "%s" % 0x680067,
            "ifId": "vpc-384", "encap": "vlan-101",
            "pcTag": "48934", "rw_bd": "15728629",
            "rw_mac": "aa:bb:cc:dd:ee:ff",
            "epg_name":"uni/tn-ag/ap-app/epg-e1",
            "vnid_name": "uni/tn-ag/ctx-v1"
        }, "dst": {
            "node": "%s" % 0x660065,
            "ifId": "vpc-381", "encap": "vlan-101",
            "pcTag": "48934", "rw_bd": "15728629",
            "epg_name":"uni/tn-ag/ap-app/epg-e1",
            "vnid_name": "uni/tn-ag/ctx-v1"
        }
    }
    dut = get_worker()
    dut.notify_syslog = "192.168.1.72"
    dut.notify_move_syslog = True
    dut.ep_notify_move(key, move)

def test_ept_ep_notify_fail_syslog(app):
    # send syslog for endpoint that failed to be processed
    if not manually_executing: return 
    key = {
        "addr": "10.1.4.101",
        "vnid": "2654208",
        "type": "ip"
    }
    dut = get_worker()
    dut.notify_syslog = "192.168.1.72"
    dut.ep_notify_fail(EPJob("notify_fail",key))



