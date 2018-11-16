"""
main ept worker functionality unit tests

simulated test topology


     tun102 -> 102           tun101 -> 101          tun101 -> 101          tun101 -> 101
     tun103 -> 103           tun103 -> 103          tun102 -> 102          tun102 -> 102
     tun104 -> 104           tun104 -> 104          tun104 -> 104          tun103 -> 103
                                                    tun100 -> 0x00650064   tun100 -> 0x00650064
             vpc-vtep(10.0.0.100)
    +------------+          +------------+         +------------+         +------------+
    |  leaf-101  |          |  leaf-102  |         |  leaf-103  |         |  leaf-104  |
    | 10.0.0.101 |          | 10.0.0.102 |         | 10.0.0.103 |         | 10.0.0.104 |
    +------------+          +------------+         +------------+         +------------+
     po1                     po7                     eth1/1                 eth1/1
     po2, vpc-384            po8, vpc-384             tun96 -> 10.0.0.96
     po3, vpc-385            po9, vpc-385             (vxlan-avs)

port-channel names:
    po1 = ag_po1001
    po7 = ag_po1002
    po2/po8 = ag_vpc1
    po3/po8 = ag_vpc2

tenant ag, vrf v1, bd bd1/bd2/bd3, app a1, epg e1/e2/e3
    v1  - uni/tn-ag/ctx-v1
            vnid: 0x2c8000
            pctag: 20001

    bd1 - uni/tn-ag/bd-bd1
            vnid: 0xe4ffd1
            pctag: 20011
            subnet s1v4 - uni/tn-ag/bd-bd1/subnet-[10.1.1.1/24] 
            subnet s1v6 - uni/tn-ag/bd-bd1/subnet-[2001:10:1:1::1/64] 
            epg e1 - uni/tn-ag/ap-ap/epg-e1
                pctag: 30011
                vlan-encap: 101
            epg e4 - uni/tn-ag/ap-ap/epg-e4
                pctag: 30014
                vxlan-encap: 0x8f0000

    bd2 - uni/tn-ag/bd-bd2
            vnid: 0xe4ffd2
            pctag: 20012
            subnet s2v4 - uni/tn-ag/bd-bd2/subnet-[20.1.1.1/24] 
            subnet s2v6 - uni/tn-ag/bd-bd2/subnet-[2001:20:1:1::1/64] 
            epg e2 - uni/tn-ag/ap-ap/epg-e2
                pctag: 30012
                vlan-encap: 102
        
    bd3 - uni/tn-ag/bd-bd3
            vnid: 0xe4ffd3
            pctag: 20013
            subnet s3v4 - uni/tn-ag/bd-bd3/subnet-[30.1.1.1/24] 
            subnet s3v6 - uni/tn-ag/bd-bd3/subnet-[2001:30:1:1::1/64] 
            epg e3 - uni/tn-ag/ap-ap/epg-e3
                pctag: 30013
                vlan-encap: 103
                subnet s3e3v4 - uni/tn-ag/ap-ap/epg-e3/subnet-[30.1.2.1/24]


"""
import logging
import pytest
import time

from app.models.aci.fabric import Fabric
from app.models.aci.ept.ept_msg import *
from app.models.aci.ept.ept_worker import eptWorker
from app.models.aci.ept.ept_queue_stats import eptQueueStats
from app.models.aci.ept.ept_epg import eptEpg
from app.models.aci.ept.ept_subnet import eptSubnet
from app.models.aci.ept.ept_vnid import eptVnid
from app.models.aci.ept.ept_node import eptNode
from app.models.aci.ept.ept_vpc import eptVpc
from app.models.aci.ept.ept_pc import eptPc
from app.models.aci.ept.ept_tunnel import eptTunnel
from app.models.aci.ept.ept_history import eptHistory
from app.models.aci.ept.ept_history import eptHistoryEvent
from app.models.aci.ept.ept_stale import eptStale
from app.models.aci.ept.ept_move import eptMove
from app.models.aci.ept.ept_offsubnet import eptOffSubnet
from app.models.aci.ept.ept_endpoint import eptEndpoint
from app.models.aci.ept.ept_endpoint import eptEndpointEvent
from app.models.aci.ept.ept_rapid import eptRapid
from app.models.aci.ept.ept_remediate import eptRemediate

from app.models.rest.db import db_setup
from app.models.utils import get_db
from app.models.utils import get_redis
from app.models.utils import pretty_print

# module level logging
logger = logging.getLogger(__name__)

redis = get_redis()
tfabric = "fab1"
overlay_vnid = 0xffffef
vrf_vnid = 0x2c8000
vrf_pctag = 20001
vrf_name = "uni/tn-ag/ctx-v1"
bd1_vnid = 0xe4ffd1
bd1_pctag = 20011
bd1_name = "uni/tn-ag/bd-bd1"
bd2_vnid = 0xe4ffd2
bd2_pctag = 20012
bd2_name = "uni/tn-ag/bd-bd2"
bd3_vnid = 0xe4ffd3
bd3_pctag = 20013
bd3_name = "uni/tn-ag/bd-bd3"
epg1_pctag = 30011
epg2_pctag = 30012
epg3_pctag = 30013
epg4_pctag = 30014
epg1_encap = "vlan-101"
epg2_encap = "vlan-102"
epg3_encap = "vlan-103"
epg4_encap = "vxlan-%s" % 0x8f0000
epg1_name = "uni/tn-ag/ap-ap/epg-e1"
epg2_name = "uni/tn-ag/ap-ap/epg-e2"
epg3_name = "uni/tn-ag/ap-ap/epg-e3"
epg4_name = "uni/tn-ag/ap-ap/epg-e4"
# per node, which port-channels are vpcs
vpc_intf = {
    101: ["po2", "po3"],
    102: ["po8", "po9"],
}

parser = eptEpmEventParser(tfabric, overlay_vnid)

@pytest.fixture(scope="module")
def app(request):
    # module level setup
    from app import create_app
    app = create_app("config.py")
    db = get_db()
    logger.debug("setting up db!")
    assert db_setup(sharding=False, force=True)
    logger.debug("db initialized")

    create_test_environment()

    # teardown called after all tests in session have completed
    def teardown(): 
        # delete everything!
        #db = get_db()
        #db.client.drop_database("testdb")
        pass

    request.addfinalizer(teardown)
    logger.debug("(%s) module level app setup completed", __name__)
    return app

@pytest.fixture(scope="function")
def func_prep(request, app):
    # perform proper proper prep/cleanup
    # will delete all mo objects we're using as part of dependency testing
    logger.debug("%s %s setup", "."*80, __name__)

    def teardown(): 
        logger.debug("%s %s teardown", ":"*80, __name__)
        eptQueueStats.delete(_filters={})
        # deleting eptEndpoint triggers delete for appropriate dependent objects
        # (history, stale, offsubnet, move, rapid, remediate)
        eptEndpoint.delete(_filters={})
        redis.flushall()
        
    request.addfinalizer(teardown)
    return

def create_test_environment():
    # create simulated enviroment in doc string
    assert Fabric.load(fabric=tfabric).save()

    def create_node(node,name=None,addr=None,role="leaf",peer=0,nodes=[]):
        if name is None: name="leaf-%s" % node
        if addr is None: addr = "10.0.0.%s" % node
        assert eptNode.load(fabric=tfabric, state="in-service", pod_id=1,
                node=node,
                name=name,
                role=role,
                addr=addr,
                peer=peer,
                nodes=nodes
        ).save()
    def create_tunnel(node,remote,src=None,dst=None,intf=None,encap="ivxlan",flags="physical"):
        # create tunnels to all other nodes except this one
        assert eptTunnel.load(fabric=tfabric, status="up", encap="ivxlan", flags="physical", 
                node=node,
                src="10.0.0.%s" % node if src is None else src,
                dst="10.0.0.%s" % remote if dst is None else dst,
                intf=intf if intf is not None else "tunnel%s" % remote,
                remote=remote,
        ).save()

    create_node(101,peer=102)
    create_node(102,peer=101)
    create_node(0x650066, addr="10.0.0.100", name="vpc-domain-1", role="vpc", nodes=[
            {"node": 101, "addr":"10.0.0.101"},
            {"node": 102, "addr":"10.0.0.102"},
        ])
    create_node(103)
    create_node(104)
    # full mesh
    for s in [101,102,103,104]:
        for d in [101,102,103,104]:
            if s!=d:
                create_tunnel(s,d)
    # vpc tunnels
    create_tunnel(103, 0x650066, dst="10.0.0.100", intf="tunnel100")
    create_tunnel(104, 0x650066, dst="10.0.0.100", intf="tunnel100")
    # create vxlan tunnel to local host
    create_tunnel(103, 0, src="10.0.0.32", dst="10.0.0.96", intf="tunnel96", encap="vxlan",flags="virtual")

    # create port-channels and vpcs
    assert eptPc.load(fabric=tfabric,node=101,intf="po1",intf_name="ag_po1001",name="topology/pod-1/node-101/sys/aggr-[po1]").save()
    assert eptPc.load(fabric=tfabric,node=101,intf="po2",intf_name="ag_vpc1",name="topology/pod-1/node-101/sys/aggr-[po2]").save()
    assert eptPc.load(fabric=tfabric,node=101,intf="po3",intf_name="ag_vpc2",name="topology/pod-1/node-101/sys/aggr-[po3]").save()
    assert eptVpc.load(fabric=tfabric,node=101,intf="po2",vpc=384,name="topology/pod-1/node-101/sys/vpc/inst/dom-1/if-384/rsvpcConf").save()
    assert eptVpc.load(fabric=tfabric,node=101,intf="po3",vpc=385,name="topology/pod-1/node-101/sys/vpc/inst/dom-1/if-385/rsvpcConf").save()
    assert eptPc.load(fabric=tfabric,node=102,intf="po7",intf_name="ag_po1002",name="topology/pod-1/node-102/sys/aggr-[po7]").save()
    assert eptPc.load(fabric=tfabric,node=102,intf="po8",intf_name="ag_vpc1",name="topology/pod-1/node-102/sys/aggr-[po8]").save()
    assert eptPc.load(fabric=tfabric,node=102,intf="po9",intf_name="ag_vpc2",name="topology/pod-1/node-102/sys/aggr-[po9]").save()
    assert eptVpc.load(fabric=tfabric,node=102,intf="po8",vpc=384,name="topology/pod-1/node-102/sys/vpc/inst/dom-1/if-384/rsvpcConf").save()
    assert eptVpc.load(fabric=tfabric,node=102,intf="po9",vpc=385,name="topology/pod-1/node-102/sys/vpc/inst/dom-1/if-385/rsvpcConf").save()

    # create vnids for vrfs and bds
    assert eptVnid.load(fabric=tfabric,name=vrf_name,vrf=vrf_vnid,vnid=vrf_vnid,pctag=vrf_pctag).save()
    assert eptVnid.load(fabric=tfabric,name=bd1_name,vrf=vrf_vnid,vnid=bd1_vnid,pctag=bd1_pctag).save()
    assert eptVnid.load(fabric=tfabric,name=bd2_name,vrf=vrf_vnid,vnid=bd2_vnid,pctag=bd2_pctag).save()
    assert eptVnid.load(fabric=tfabric,name=bd3_name,vrf=vrf_vnid,vnid=bd3_vnid,pctag=bd3_pctag).save()
    # create epgs
    assert eptEpg.load(fabric=tfabric,name=epg1_name,vrf=vrf_vnid,pctag=epg1_pctag,bd=bd1_vnid).save()
    assert eptEpg.load(fabric=tfabric,name=epg2_name,vrf=vrf_vnid,pctag=epg2_pctag,bd=bd2_vnid).save()
    assert eptEpg.load(fabric=tfabric,name=epg3_name,vrf=vrf_vnid,pctag=epg3_pctag,bd=bd3_vnid).save()
    assert eptEpg.load(fabric=tfabric,name=epg4_name,vrf=vrf_vnid,pctag=epg4_pctag,bd=bd1_vnid).save()
    # create subnets
    assert eptSubnet.load(fabric=tfabric,name="%s/subnet-[10.1.1.1/24]"%bd1_name,bd=bd1_vnid,ip="10.1.1.1/24").save()
    assert eptSubnet.load(fabric=tfabric,name="%s/subnet-[2001:10:1:1::1/64]"%bd1_name,bd=bd1_vnid,ip="2001:10:1:1::1/64").save()
    assert eptSubnet.load(fabric=tfabric,name="%s/subnet-[20.1.1.1/24]"%bd2_name,bd=bd2_vnid,ip="20.1.1.1/24").save()
    assert eptSubnet.load(fabric=tfabric,name="%s/subnet-[2001:20:1:1::1/64]"%bd2_name,bd=bd2_vnid,ip="2001:20:1:1::1/64").save()
    assert eptSubnet.load(fabric=tfabric,name="%s/subnet-[30.1.1.1/24]"%bd3_name,bd=bd3_vnid,ip="30.1.1.1/24").save()
    assert eptSubnet.load(fabric=tfabric,name="%s/subnet-[2001:30:1:1::1/64]"%bd3_name,bd=bd3_vnid,ip="2001:30:1:1::1/64").save()
    # epg subnet
    assert eptSubnet.load(fabric=tfabric,name="%s/subnet-[30.1.2.1/24]"%epg3_name,bd=bd3_vnid,ip="30.1.2.1/24").save()

def test_epm_parser_parse_basic(app, func_prep):
    # parse epmIp, epmMacEp, and epmRsMacEpToIpEpAtt objects
    logger.debug("parse epmMacEp object")
    msg = parser.parse("epmMacEp", {
        "dn": "topology/pod-1/node-101/sys/ctx-[vxlan-2916352]/bd-[vxlan-15007704]/vlan-[vlan-101]/db-ep/mac-00:00:40:01:01:01",
        "ifId": "po1",
        "flags": "ip,local,mac,peer-aged,vpc-attached",
        "pcTag": "32771",
        "status": "modified"
    }, 1.0)
    logger.debug(msg)
    assert msg.addr == "00:00:40:01:01:01"
    assert msg.ts == 1.0
    assert msg.classname == "epmMacEp"
    assert msg.type == "mac"
    assert msg.status == "modified"
    assert msg.flags == ["ip","local","mac","peer-aged","vpc-attached"]
    assert msg.ifId == "po1"
    assert msg.pcTag == 32771
    assert msg.encap == "vlan-101"
    assert msg.ip == ""
    assert msg.node == 101
    assert msg.vnid == 15007704
    assert msg.vrf == 2916352
    assert msg.bd == 15007704
    assert msg.wt == WORK_TYPE.EPM_MAC_EVENT

    logger.debug("parse epmIpEp object")
    msg = parser.parse("epmIpEp", {
        "dn": "topology/pod-1/node-101/sys/ctx-[vxlan-2916352]/bd-[vxlan-15007704]/vlan-[vlan-101]/db-ep/ip-[10.1.1.101]",
        "flags": "local,vpc-attached",
        "ifId": "po2",
        "pcTag": "32771",
        "status": "created",
    }, 1.0)
    logger.debug(msg)
    assert msg.addr == "10.1.1.101"
    assert msg.ts == 1.0
    assert msg.classname == "epmIpEp"
    assert msg.type == "ip"
    assert msg.status == "created"
    assert msg.flags == ["local", "vpc-attached"]
    assert msg.ifId == "po2"
    assert msg.pcTag == 32771
    assert msg.encap == "vlan-101"
    assert msg.ip == ""
    assert msg.node == 101
    assert msg.vnid == 2916352
    assert msg.vrf == 2916352
    assert msg.bd == 15007704
    assert msg.wt == WORK_TYPE.EPM_IP_EVENT


    logger.debug("parse epmRsMacEpToIpEpAtt object")
    msg = parser.parse("epmRsMacEpToIpEpAtt", {
        "dn": "topology/pod-1/node-101/sys/ctx-[vxlan-2916352]/bd-[vxlan-15007704]/vlan-[vlan-101]/db-ep/mac-00:00:40:01:01:01/rsmacEpToIpEpAtt-[sys/ctx-[vxlan-2916352]/bd-[vxlan-15007704]/vlan-[vlan-101]/db-ep/ip-[10.1.1.101]]",
    }, 1.0)
    logger.debug(msg)
    assert msg.addr == "00:00:40:01:01:01"
    assert msg.ts == 1.0
    assert msg.classname == "epmRsMacEpToIpEpAtt"
    assert msg.type == "ip"
    assert msg.status == "created"
    assert msg.flags == []
    assert msg.ifId == ""
    assert msg.pcTag == 0
    assert msg.encap == "vlan-101"
    assert msg.ip == "10.1.1.101"
    assert msg.node == 101
    assert msg.vnid == 2916352
    assert msg.vrf == 2916352
    assert msg.bd == 15007704
    assert msg.wt == WORK_TYPE.EPM_RS_IP_EVENT

def get_epg_encap_pctag_vnid(val):
    # return tuple (encap, pctag, bd_vnid) for this bd or epg (assume epg if epg=True)
    if val is None or val == 1 or val == 4:
        return (epg1_encap, epg1_pctag, bd1_vnid)
    elif val == 2:
        return (epg2_encap, epg2_pctag, bd2_vnid)
    elif val == 3:
        return (epg3_encap, epg3_pctag, bd3_vnid)
    else:
        raise Exception("unknown epg/bd val %s" % val)

def get_epm_event(node, addr, ip=None, wt=WORK_TYPE.EPM_IP_EVENT, remote_node=None, bd=None, 
        epg=None, intf=None, status="created", flags=None, pctag=None, ts=1.0):
    # based on static topology create an event for the params provided
    #   * work type EPM_IP_EVENT, EPM_MAC_EVENT, or EPM_RS_IP_EVENT
    #   * for EPM_RS_IP_EVENT, both mac and ip are required
    #   *
    #       if remote_node is none then this assumes a local event
    #           local event requires intf for created events
    #       else, map remote node to appropriate interface so caller does not need to worry about it
    #   *
    #       if bd is not provided, then assumes bd1 (with auto account for local or XR)
    #       if epg is not provided, then assume epg1 (wiht auto account for local or XR)
    #   *
    #       if flags are not provided, then following assumptions are made:
    #           if local
    #               add local flag
    #               if interface is vpc, add vpc-attached
    #           if endpoint is mac, add mac flag
    #           if endpoint is ip, no flags by default (unless local)
    #

    if epg is not None: (encap, epg_pctag, bd_vnid) = get_epg_encap_pctag_vnid(epg)
    else: (encap, epg_pctag, bd_vnid) = get_epg_encap_pctag_vnid(bd)
    if "vxlan" in encap: encap_str = "vxlan-[%s]" % encap
    else: encap_str = "vlan-[%s]" % encap

    dn = "topology/pod-1/node-%s/sys/ctx-[vxlan-%s]" % (node, vrf_vnid)
    if wt == WORK_TYPE.EPM_RS_IP_EVENT:
        # only need dn whic assumes local event
        assert ip is not None
        logger.debug("creating epmRsMacEpToIpEpAtt object")
        rs = "sys/ctx-[vxlan-%s]/bd-[vxlan-%s]/%s/db-ep/ip-[%s]" %(vrf_vnid, bd_vnid, encap_str, ip)
        dn = "%s/bd-[vxlan-%s]/%s/db-ep/mac-%s/rsmacEpToIpEpAtt-[%s]"%(dn,bd_vnid,encap_str,addr,rs)
        return parser.parse("epmRsMacEpToIpEpAtt", {"dn": dn, "status": status}, ts)

    else:
        data = {"status": status}
        addr_str = "ip-[%s]"%addr if wt==WORK_TYPE.EPM_IP_EVENT else "mac-[%s]" % addr
        if remote_node is None:
            # this is a local event
            data["dn"] = "%s/bd-[vxlan-%s]/%s/db-ep/%s" % (dn, bd_vnid, encap_str, addr_str)
        else:
            if wt==WORK_TYPE.EPM_MAC_EVENT:
                # bd vnid required for l2 xr
                dn = "%s/bd-[vxlan-%s]" % bd_vnid
            data["dn"] = "%s/db-ep/%s" % (dn, addr_str)
        # if status is created, then need flags, ifId and pcTag. Else use whatever was provided
        if status == "created":
            # get ifId
            if intf is None:
                # required on local - can't guess this one...
                if remote_node is None:
                    raise Exception("local create requires an intf")
                # map intf to tunnel
                intf = {
                    101: "tunnel101",
                    102: "tunnel102",
                    103: "tunnel103",
                    104: "tunnel104",
                    0x650066: "tunnel100",
                }.get(remote_node, None)
                if intf is None:
                    raise Exception("unable to map remote_node %s to an interface" % remote_node)
            data["ifId"] = intf
            # get pctag
            if pctag is None:
                # use the epg pctag already pulled
                pctag = epg_pctag
            data["pcTag"] = pctag
            # set the flags
            if flags is None or len(flags)==0: 
                flags = []
                if remote_node is None and node in vpc_intf and intf in vpc_intf[node]:
                    # add vpc-attached flag for local vpc interface 
                    flags.append("vpc-attached")

            # always set mac flag for mac events, even if user provided flags
            if wt==WORK_TYPE.EPM_MAC_EVENT and "mac" not in flags: flags.append("mac")
            if remote_node is not None:
                # XR ip always has 'ip' flag
                if wt==WORK_TYPE.EPM_IP_EVENT and "ip" not in flags: flags.append("ip")
            else:
                # for local events, local flag always set
                if "local" not in flags: flags.append("local")
            data["flags"] = ",".join(flags)
        else:
            # only add the fields provided by caller
            if flags is not None:
                data["flags"] = ",".join(flags)
            if intf is not None:
                data["ifId"] = intf
            if pctag is not None:
                data["pcTag"] = pctag

        # now all data is ready, create the event
        classname = "epmIpEp" if wt==WORK_TYPE.EPM_IP_EVENT else "epmMacEp"
        logger.debug("creating %s object", classname)
        return parser.parse(classname, data, ts)

def get_worker(role="worker"):
    # get a worker to handle event 
    dut = eptWorker("w1", role)
    # need to setup db and redis
    dut.db = get_db()
    dut.redis = get_redis()
    return dut

def test_handle_endpoint_event_new_local_mac(app, func_prep):
    # create event for new mac and ensure entry is added to eptHistory and eptEndpoint tables
    dut = get_worker()
    addr = "00:00:01:02:03:04"
    msg = get_epm_event(101, addr, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="po2")
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # ensure eptHistory and eptEndpoint objects are created
    h = eptHistory.find(fabric=tfabric, addr=addr)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert h.addr == addr
    assert h.node == 101
    assert h.vnid == bd1_vnid
    assert h.type == "mac"
    assert not h.is_stale and not h.is_offsubnet 
    assert h.count == 1
    assert len(h.events) == 1
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.classname == "epmMacEp"
    assert e.status == "created"
    assert e.remote == 0
    assert e.pctag == epg1_pctag
    assert e.encap == epg1_encap
    assert e.intf_id == "vpc-384"       # vpc interface re-mapped
    assert e.intf_name == "ag_vpc1"
    assert e.rw_mac == ""
    assert e.rw_bd == 0
    assert e.vnid_name == bd1_name
    assert e.epg_name == epg1_name

    endpoint = eptEndpoint.find(fabric=tfabric, addr=addr)
    assert len(endpoint) == 1
    e = endpoint[0]
    logger.debug(pretty_print(e.to_json()))
    assert e.addr == addr
    assert e.vnid == bd1_vnid
    assert e.type == "mac"
    assert not e.is_stale and not e.is_offsubnet  and not e.is_rapid
    assert e.count == 1
    assert len(e.events) == 1
    e = eptEndpointEvent.from_dict(e.events[0])
    assert e.status == "created"
    assert e.pctag == epg1_pctag
    assert e.encap == epg1_encap
    assert e.intf_id == "vpc-384"       # vpc interface re-mapped
    assert e.intf_name == "ag_vpc1"
    assert e.rw_mac == ""
    assert e.rw_bd == 0
    assert e.vnid_name == bd1_name
    assert e.epg_name == epg1_name


def test_handle_endpoint_event_new_local_ipv4(app, func_prep):
    # create event for new ip and ensure entry is added to eptHistory and eptEndpoint tables
    dut = get_worker()
    addr = "10.1.1.101"
    msg = get_epm_event(101, addr, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="po2")
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # ensure eptHistory and eptEndpoint objects are created
    h = eptHistory.find(fabric=tfabric, addr=addr)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert h.addr == addr
    assert h.node == 101
    assert h.vnid == vrf_vnid
    assert h.type == "ip"
    assert not h.is_stale and not h.is_offsubnet 
    assert h.count == 1
    assert len(h.events) == 1
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.classname == "epmIpEp"
    assert e.status == "created"
    assert e.remote == 0
    assert e.pctag == epg1_pctag
    assert e.encap == epg1_encap
    assert e.intf_id == "vpc-384"       # vpc interface re-mapped
    assert e.intf_name == "ag_vpc1"
    assert e.rw_mac == ""
    assert e.rw_bd == 0
    assert e.vnid_name == vrf_name
    assert e.epg_name == epg1_name

    # generally, eptEndpoint would not be created because the local event is not complete (no 
    # rewrite info is present).  However, to support svi/cached endpoints that may never have
    # rewrite info, the first event will always create an eptEndpoint entry
    endpoint = eptEndpoint.find(fabric=tfabric, addr=addr)
    assert len(endpoint) == 1
    e = endpoint[0]
    logger.debug(pretty_print(e.to_json()))
    assert e.addr == addr
    assert e.vnid == vrf_vnid
    assert e.type == "ipv4"
    assert not e.is_stale and not e.is_offsubnet  and not e.is_rapid
    assert e.count == 0
    assert len(e.events) == 0

def test_handle_endpoint_event_new_local_ipv4_with_rewrite(app, func_prep):
    # create event for new ip followed by rewrite info and ensure entry is added correctly
    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="po2")
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # ensure eptHistory and eptEndpoint objects are created
    h = eptHistory.find(fabric=tfabric, addr=ip)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert h.addr == ip
    assert h.node == 101
    assert h.vnid == vrf_vnid
    assert h.type == "ip"
    assert not h.is_stale and not h.is_offsubnet 
    assert h.count == 2
    assert len(h.events) == 2
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.classname == "epmRsMacEpToIpEpAtt"
    assert e.status == "created"
    assert e.remote == 0
    assert e.pctag == epg1_pctag
    assert e.encap == epg1_encap
    assert e.intf_id == "vpc-384"       # vpc interface re-mapped
    assert e.intf_name == "ag_vpc1"
    assert e.rw_mac == mac
    assert e.rw_bd == bd1_vnid
    assert e.vnid_name == vrf_name
    assert e.epg_name == epg1_name

    endpoint = eptEndpoint.find(fabric=tfabric, addr=ip)
    assert len(endpoint) == 1
    e = endpoint[0]
    logger.debug(pretty_print(e.to_json()))
    assert e.addr == ip
    assert e.vnid == vrf_vnid
    assert e.type == "ipv4"
    assert not e.is_stale and not e.is_offsubnet  and not e.is_rapid
    assert e.count == 1
    assert len(e.events) == 1
    e = eptEndpointEvent.from_dict(e.events[0])
    assert e.status == "created"
    assert e.pctag == epg1_pctag
    assert e.encap == epg1_encap
    assert e.intf_id == "vpc-384"       # vpc interface re-mapped
    assert e.intf_name == "ag_vpc1"
    assert e.rw_mac == mac
    assert e.rw_bd == bd1_vnid
    assert e.vnid_name == vrf_name
    assert e.epg_name == epg1_name


