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
     po3, vpc-385            po9, vpc-385             (orphan VL)
               tun901    tun902          
                  10.0.0.90
             (VL behind vpc)

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
from app.models.aci.ept.ept_move import eptMoveEvent
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
vpc_node_id = 0x650066

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
    #
    logger.debug("%s create_environment setup", "."*80)
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
        # need to auto-calculate the dn name
        intf = intf if intf is not None else "tunnel%s" % remote
        dn = "topology/pod-1/node-%s/sys/tunnel-[%s]" % (node, intf)
        assert eptTunnel.load(fabric=tfabric, name=dn, status="up", encap=encap, flags=flags, 
                node=node,
                src="10.0.0.%s" % node if src is None else src,
                dst="10.0.0.%s" % remote if dst is None else dst,
                intf=intf,
                remote=remote,
        ).save()

    create_node(101,peer=102)
    create_node(102,peer=101)
    create_node(vpc_node_id, addr="10.0.0.100", name="vpc-domain-1", role="vpc", nodes=[
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
    create_tunnel(103, vpc_node_id, dst="10.0.0.100", intf="tunnel100")
    create_tunnel(104, vpc_node_id, dst="10.0.0.100", intf="tunnel100")
    # create vxlan tunnel to local host
    create_tunnel(101,0,src="10.0.0.32",dst="10.0.0.90",intf="tunnel901",encap="vxlan",flags="virtual")
    create_tunnel(102,0,src="10.0.0.32",dst="10.0.0.90",intf="tunnel902",encap="vxlan",flags="virtual")
    create_tunnel(103,0,src="10.0.0.32",dst="10.0.0.96",intf="tunnel96", encap="vxlan",flags="virtual")

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
        
    logger.debug("%s create_environment complete", ":"*80)

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
        msg = parser.parse("epmRsMacEpToIpEpAtt", {"dn": dn, "status": status}, ts)

    else:
        data = {"status": status}
        addr_str = "ip-[%s]"%addr if wt==WORK_TYPE.EPM_IP_EVENT else "mac-[%s]" % addr
        if remote_node is None:
            # this is a local event
            data["dn"] = "%s/bd-[vxlan-%s]/%s/db-ep/%s" % (dn, bd_vnid, encap_str, addr_str)
        else:
            if wt==WORK_TYPE.EPM_MAC_EVENT:
                # bd vnid required for l2 xr
                dn = "%s/bd-[vxlan-%s]" % (dn, bd_vnid)
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
                    vpc_node_id: "tunnel100",
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
        msg = parser.parse(classname, data, ts)
    logger.debug("[w1] %s" % msg)
    return msg

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

def test_handle_endpoint_event_new_local_ipv4_with_rewrite_out_of_order(app, func_prep):
    # create event for rewrite followed by epmIpEm and ensure entry is correct 
    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="po2")
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
    assert e.classname == "epmIpEp"
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

def test_handle_endpoint_event_new_local_ipv6_with_rewrite(app, func_prep):
    # create event for new ip followed by rewrite info and ensure entry is added correctly
    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "2001:10:1:1::101"
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
    assert e.type == "ipv6"
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

def test_handle_endpoint_event_ignore_delete_for_non_existing_endpoint(app, func_prep):
    # send delete and then modify for non-existing endpoint and ensure no history/endpoint event
    # is created

    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"

    # first test for mac
    msg = get_epm_event(101, mac, wt=WORK_TYPE.EPM_MAC_EVENT, status="deleted")
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, wt=WORK_TYPE.EPM_MAC_EVENT, status="modified")
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    h = eptHistory.find(fabric=tfabric, addr=mac)
    assert len(h)==0
    endpoint = eptEndpoint.find(fabric=tfabric, addr=mac)
    assert len(endpoint) == 0

    # repeat for ip and rs_ip events
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="deleted")
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="modified")
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, status="deleted")
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, status="modified")
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    h = eptHistory.find(fabric=tfabric, addr=ip)
    assert len(h)==0
    endpoint = eptEndpoint.find(fabric=tfabric, addr=ip)
    assert len(endpoint) == 0

def test_handle_endpoint_event_new_xr_mac(app, func_prep):
    # create an xr mac and ensure eptHistory and eptEndpoint object are created with correct info
    dut = get_worker()
    mac = "00:00:01:02:03:04"
    
    msg = get_epm_event(103, mac, wt=WORK_TYPE.EPM_MAC_EVENT, remote_node=101)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # ensure eptHistory and eptEndpoint objects are created
    h = eptHistory.find(fabric=tfabric, addr=mac)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert h.addr == mac
    assert h.node == 103
    assert h.vnid == bd1_vnid
    assert h.type == "mac"
    # note, is_stale analysis skipped on mac along with is_offsubnet...
    # should be false but if mac stale analysis is enabled in future, we will write explicit test
    # cases for it.
    #assert not h.is_stale and not h.is_offsubnet 
    assert h.count == 1
    assert len(h.events) == 1
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.classname == "epmMacEp"
    assert e.status == "created"
    assert e.remote == 101
    assert e.pctag == epg1_pctag
    assert e.encap == ""
    assert e.intf_id == "tunnel101"
    assert e.intf_name == "tunnel101"
    assert e.rw_mac == ""
    assert e.rw_bd == 0
    assert e.vnid_name == bd1_name
    assert e.epg_name == epg1_name

    # XR with no local entry, eptEndpoint should exist but no events
    endpoint = eptEndpoint.find(fabric=tfabric, addr=mac)
    assert len(endpoint) == 1
    e = endpoint[0]
    logger.debug(pretty_print(e.to_json()))
    assert e.addr == mac
    assert e.vnid == bd1_vnid
    assert e.type == "mac"
    assert not e.is_stale and not e.is_offsubnet  and not e.is_rapid
    assert e.count == 0
    assert len(e.events) == 0

def test_handle_endpoint_event_new_xr_ipv4_vpc(app, func_prep):
    # create an xr ipv4 and ensure eptHistory and eptEndpoint object are created with correct info
    dut = get_worker()
    ip = "10.1.1.101"

    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, remote_node=vpc_node_id)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # ensure eptHistory and eptEndpoint objects are created
    h = eptHistory.find(fabric=tfabric, addr=ip)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert h.addr == ip
    assert h.node == 103
    assert h.vnid == vrf_vnid
    assert h.type == "ip"
    # this is XR with no local endpoint, that is stale but will have explicitly tests for stale 
    #assert not h.is_offsubnet and assert h.is_stale
    assert h.count == 1
    assert len(h.events) == 1
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.classname == "epmIpEp"
    assert e.status == "created"
    assert e.remote == vpc_node_id
    assert e.pctag == epg1_pctag
    assert e.encap == ""
    assert e.intf_id == "tunnel100"
    assert e.intf_name == "tunnel100"
    assert e.rw_mac == ""
    assert e.rw_bd == 0
    assert e.vnid_name == vrf_name
    assert e.epg_name == epg1_name

    # XR with no local entry, eptEndpoint should exist but no events
    endpoint = eptEndpoint.find(fabric=tfabric, addr=ip)
    assert len(endpoint) == 1
    e = endpoint[0]
    logger.debug(pretty_print(e.to_json()))
    assert e.addr == ip
    assert e.vnid == vrf_vnid
    assert e.type == "ipv4"
    # stale set by watcher - will have specific tests for stale checks
    # assert not e.is_stale and not e.is_offsubnet  and not e.is_rapid
    assert e.count == 0
    assert len(e.events) == 0

def test_handle_endpoint_event_learn_on_both_vpc_nodes_no_move_event(app, func_prep):
    # trigger a learn on node-101 on vpc interface and then on node-102 on same vpc interface and
    # ensure no move is generated. Two eptHistory events (one for each node) and only one 
    # eptEndpoint event pointing to vpc_node_id as local node
    
    dut = get_worker()
    mac = "00:00:01:02:03:04"

    # first test for mac
    msg = get_epm_event(101, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="po2")
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="po8")
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    h = eptHistory.find(fabric=tfabric, addr=mac, node=101)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 1
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert e.intf_id == "vpc-384"
    assert e.intf_name == "ag_vpc1"

    h = eptHistory.find(fabric=tfabric, addr=mac, node=102)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 1
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert e.intf_id == "vpc-384"
    assert e.intf_name == "ag_vpc1"

    endpoint = eptEndpoint.find(fabric=tfabric, addr=mac)
    assert len(endpoint) == 1
    e = endpoint[0]
    logger.debug(pretty_print(e.to_json()))
    assert e.addr == mac
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

    # no moves found
    m = eptMove.find(fabric=tfabric, addr=mac)
    assert len(m) == 0

def validate_mac_state_1():
    # final state for following tests:
    #   test_handle_endpoint_event_basic_mac_move 
    #   test_handle_endpoint_event_basic_mac_move_transitory_delete (out of order)

    mac = "00:00:01:02:03:04"
    h = eptHistory.find(fabric=tfabric, addr=mac, node=103)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 3
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert e.remote == 104
    assert e.intf_id == "tunnel104"
    assert "bounce" in e.flags

    h = eptHistory.find(fabric=tfabric, addr=mac, node=104)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 1
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert "local" in e.flags

    endpoint = eptEndpoint.find(fabric=tfabric, addr=mac)
    assert len(endpoint) == 1
    e = endpoint[0]
    logger.debug(pretty_print(e.to_json()))
    assert e.count == 2
    assert len(e.events) == 2
    e0 = eptEndpointEvent.from_dict(e.events[0])
    assert e0.node == 104
    assert e0.intf_id == "eth1/1"
    e1 = eptEndpointEvent.from_dict(e.events[1])
    assert e1.node == 103
    assert e1.intf_id == "eth1/1"

    # ensure move event was created
    move = eptMove.find(fabric=tfabric, addr=mac)
    assert len(move) == 1
    move = move[0]
    logger.debug(pretty_print(move.to_json()))
    assert move.count == 1
    assert len(move.events) == 1
    src = eptMoveEvent.from_dict(move.events[0]["src"])
    dst = eptMoveEvent.from_dict(move.events[0]["dst"])
    assert src.node == 103
    assert src.intf_id == "eth1/1"
    assert src.intf_name == "eth1/1"
    assert src.pctag == epg1_pctag
    assert src.encap == epg1_encap
    assert src.rw_mac == ""
    assert src.rw_bd == 0
    assert src.epg_name == epg1_name
    assert src.vnid_name == bd1_name
    assert dst.node == 104
    assert dst.intf_id == "eth1/1"
    assert dst.intf_name == "eth1/1"
    assert dst.pctag == epg1_pctag
    assert dst.encap == epg1_encap
    assert dst.rw_mac == ""
    assert dst.rw_bd == 0
    assert dst.epg_name == epg1_name
    assert dst.vnid_name == bd1_name


def test_handle_endpoint_event_basic_mac_move(app, func_prep):
    # trigger move event between node 103 and node 104. Generally we see create on node 103, followed
    # by create on node 104, then delete on node-103, followed by create on node-103 with bounce
    
    dut = get_worker()
    mac = "00:00:01:02:03:04"
    msg = get_epm_event(103, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="eth1/1", ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(104, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="eth1/1", ts=2.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, mac, wt=WORK_TYPE.EPM_MAC_EVENT, status="deleted", ts=2.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, mac, wt=WORK_TYPE.EPM_MAC_EVENT, status="created", ts=2.2, 
            remote_node=104, flags=["bounce","mac"])
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    validate_mac_state_1()

def test_handle_endpoint_event_basic_mac_move_transitory_delete(app, func_prep):
    # trigger move event between node 103 and node 104. Generally we see create on node 103, followed
    # by create on node 104, then delete on node-103, followed by create on node-103 with bounce.
    # For this test case, we will have create on node-103, followed by delete on node-103, and then
    # create on node-103 with bounce, finally followed by create on node-104.  The transitory delete
    # timer should overwrite the delete in the eptEndpoint allowing move detection to correctly
    # trigger.
    
    dut = get_worker()
    mac = "00:00:01:02:03:04"
    msg = get_epm_event(103, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="eth1/1", ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, mac, wt=WORK_TYPE.EPM_MAC_EVENT, status="deleted", ts=2.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, mac, wt=WORK_TYPE.EPM_MAC_EVENT, status="created", ts=2.2, 
            remote_node=104, flags=["bounce","mac"])
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(104, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="eth1/1", ts=3.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    validate_mac_state_1()

def validate_ip_state_2():
    # final state for following tests:
    #   test_handle_endpoint_event_basic_ipv4_move_scenario_1
    #   test_handle_endpoint_event_basic_ipv4_move_scenario_2

    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"
    h = eptHistory.find(fabric=tfabric, addr=ip, node=103)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 5
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert e.remote == 104
    assert e.pctag == epg1_pctag
    assert e.rw_mac == ""
    assert e.rw_bd == 0
    assert e.intf_id == "tunnel104"
    assert e.epg_name == epg1_name
    assert e.vnid_name == vrf_name
    assert "bounce" in e.flags

    h = eptHistory.find(fabric=tfabric, addr=ip, node=104)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 2
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert e.remote == 0
    assert e.pctag == epg1_pctag
    assert e.rw_mac == mac
    assert e.rw_bd == bd1_vnid
    assert e.intf_id == "eth1/1"
    assert e.epg_name == epg1_name
    assert e.vnid_name == vrf_name
    assert "local" in e.flags

    endpoint = eptEndpoint.find(fabric=tfabric, addr=ip)
    assert len(endpoint) == 1
    e = endpoint[0]
    logger.debug(pretty_print(e.to_json()))
    assert e.count == 2
    assert len(e.events) == 2
    e0 = eptEndpointEvent.from_dict(e.events[0])
    assert e0.node == 104
    assert e0.intf_id == "eth1/1"
    e1 = eptEndpointEvent.from_dict(e.events[1])
    assert e1.node == 103
    assert e1.intf_id == "eth1/1"

    # ensure move event was created
    move = eptMove.find(fabric=tfabric, addr=ip)
    assert len(move) == 1
    move = move[0]
    logger.debug(pretty_print(move.to_json()))
    assert move.count == 1
    assert len(move.events) == 1
    src = eptMoveEvent.from_dict(move.events[0]["src"])
    dst = eptMoveEvent.from_dict(move.events[0]["dst"])
    assert src.node == 103
    assert src.intf_id == "eth1/1"
    assert src.intf_name == "eth1/1"
    assert src.pctag == epg1_pctag
    assert src.encap == epg1_encap
    assert src.rw_mac == mac
    assert src.rw_bd == bd1_vnid
    assert src.epg_name == epg1_name
    assert src.vnid_name == vrf_name
    assert dst.node == 104
    assert dst.intf_id == "eth1/1"
    assert dst.intf_name == "eth1/1"
    assert dst.pctag == epg1_pctag
    assert dst.encap == epg1_encap
    assert dst.rw_mac == mac
    assert dst.rw_bd == bd1_vnid
    assert dst.epg_name == epg1_name
    assert dst.vnid_name == vrf_name

def test_handle_endpoint_event_basic_ipv4_move_scenario_1(app, func_prep):
    # trigger move event between node 103 and node 104.
    # - local create on node-103, with rs_ip_event before ip_event
    # - create of ip_event on node-104
    # - create of rs_ip_event on node-104
    # - delete of rs_ip_event on node-103
    # - delete of ip_event on node-103
    # - create of ip_event on node-103 with bounce

    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="eth1/1", ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, ts=1.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    msg = get_epm_event(104, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="eth1/1", ts=2.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(104, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, ts=2.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    msg = get_epm_event(103, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, status="deleted", ts=2.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="deleted", ts=2.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="created", ts=2.3,
            remote_node=104, flags=["bounce"])
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    validate_ip_state_2()

def test_handle_endpoint_event_basic_ipv4_move_scenario_2(app, func_prep):
    # trigger move event between node 103 and node 104. 
    # - local create on node-103, with rs_ip_event before ip_event
    # - delete of rs_ip_event on node-103
    # - create of rs_ip_event on node-104
    # - delete of ip_event on node-103
    # - create of ip_event on node-103 with bounce
    # - create of ip_event on node-104
   
    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="eth1/1", ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, ts=1.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, status="deleted", ts=2.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(104, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, ts=2.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="deleted", ts=2.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="created", ts=2.4,
            remote_node=104, flags=["bounce"])
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(104, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="eth1/1", ts=2.5)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    validate_ip_state_2()

def test_handle_endpoint_event_basic_ipv4_move_scenario_3(app, func_prep):
    # trigger move event between node 103 and node 104. 
    # - local create on node-103, with rs_ip_event before ip_event
    # - create of ip_event on node-104
    # - delete of ip_event on node-103
    # - delete of rs_ip_event on node-103
    # - create of ip_event on node-103 with bounce
    # - create of rs_ip_event on node-104
    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"

    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="eth1/1", ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, ts=1.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(104, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="eth1/1", ts=2.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="deleted", ts=2.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, status="deleted", ts=2.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="created", ts=2.4,
            remote_node=104, flags=["bounce"])
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(104, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, ts=2.5)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    validate_ip_state_2()


def validate_mac_state_2():
    # final state for following tests:
    #   test_handle_endpoint_event_vpc_mac_move_scenario_1
    #   test_handle_endpoint_event_vpc_mac_move_scenario_2

    mac = "00:00:01:02:03:04"
    h = eptHistory.find(fabric=tfabric, addr=mac, node=101)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 3
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert e.remote == 0
    assert e.intf_id == "vpc-385"

    h = eptHistory.find(fabric=tfabric, addr=mac, node=102)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 3
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert e.remote == 0
    assert e.intf_id == "vpc-385"

    endpoint = eptEndpoint.find(fabric=tfabric, addr=mac)
    assert len(endpoint) == 1
    e = endpoint[0]
    logger.debug(pretty_print(e.to_json()))
    assert e.count == 2
    assert len(e.events) == 2
    e0 = eptEndpointEvent.from_dict(e.events[0])
    assert e0.node == vpc_node_id
    assert e0.intf_id == "vpc-385"
    e1 = eptEndpointEvent.from_dict(e.events[1])
    assert e1.node == vpc_node_id
    assert e1.intf_id == "vpc-384"

    # ensure move event was created
    move = eptMove.find(fabric=tfabric, addr=mac)
    assert len(move) == 1
    move = move[0]
    logger.debug(pretty_print(move.to_json()))
    assert move.count == 1
    assert len(move.events) == 1
    src = eptMoveEvent.from_dict(move.events[0]["src"])
    dst = eptMoveEvent.from_dict(move.events[0]["dst"])
    assert src.node == vpc_node_id
    assert src.intf_id == "vpc-384"
    assert src.intf_name == "ag_vpc1"
    assert src.pctag == epg1_pctag
    assert src.encap == epg1_encap
    assert src.rw_mac == ""
    assert src.rw_bd == 0
    assert src.epg_name == epg1_name
    assert src.vnid_name == bd1_name
    assert dst.node == vpc_node_id
    assert dst.intf_id == "vpc-385"
    assert dst.intf_name == "ag_vpc2"
    assert dst.pctag == epg1_pctag
    assert dst.encap == epg1_encap
    assert dst.rw_mac == ""
    assert dst.rw_bd == 0
    assert dst.epg_name == epg1_name
    assert dst.vnid_name == bd1_name

def test_handle_endpoint_event_vpc_mac_move_scenario_1(app, func_prep):
    # trigger a move between two vpc interfaces, one triggered on node-101 and the other on node-102
    # - create on node-101
    # - create on node-102
    # - delete on node-102
    # - create on node-102 with new interface
    # - delete on node-101
    # - create on node-101 with new interface
    dut = get_worker()
    mac = "00:00:01:02:03:04"

    # vpc-384
    msg = get_epm_event(101, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="po2", ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="po8", ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # vpc-385
    msg = get_epm_event(102, mac, wt=WORK_TYPE.EPM_MAC_EVENT, status="deleted", ts=2.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="po9", ts=2.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, wt=WORK_TYPE.EPM_MAC_EVENT, status="deleted", ts=2.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="po3", ts=2.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    validate_mac_state_2()

def test_handle_endpoint_event_vpc_mac_move_scenario_2(app, func_prep):
    # trigger a move between two vpc interfaces, one triggered on node-101 and the other on node-102
    # - create on node-101
    # - create on node-102
    # - delete on node-102
    # - delete on node-101
    # - create on node-102 with new interface
    # - create on node-101 with new interface
    dut = get_worker()
    mac = "00:00:01:02:03:04"

    # vpc-384
    msg = get_epm_event(101, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="po2", ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="po8", ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # vpc-385
    msg = get_epm_event(102, mac, wt=WORK_TYPE.EPM_MAC_EVENT, status="deleted", ts=2.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, wt=WORK_TYPE.EPM_MAC_EVENT, status="deleted", ts=2.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="po9", ts=2.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, wt=WORK_TYPE.EPM_MAC_EVENT, epg=1, intf="po3", ts=2.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    validate_mac_state_2()

def validate_ip_state_3():
    # final state for following tests:
    #   test_handle_endpoint_event_vpc_ipv4_move_scenario_1
    #   test_handle_endpoint_event_vpc_ipv4_move_scenario_2

    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"
    h = eptHistory.find(fabric=tfabric, addr=ip, node=101)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 6
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert e.remote == 0
    assert e.pctag == epg2_pctag
    assert e.rw_mac == mac
    assert e.rw_bd == bd2_vnid
    assert e.intf_id == "vpc-384"
    assert e.epg_name == epg2_name
    assert e.vnid_name == vrf_name

    h = eptHistory.find(fabric=tfabric, addr=ip, node=102)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 6
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert e.remote == 0
    assert e.pctag == epg2_pctag
    assert e.rw_mac == mac
    assert e.rw_bd == bd2_vnid
    assert e.intf_id == "vpc-384"
    assert e.epg_name == epg2_name
    assert e.vnid_name == vrf_name

    endpoint = eptEndpoint.find(fabric=tfabric, addr=ip)
    assert len(endpoint) == 1
    e = endpoint[0]
    logger.debug(pretty_print(e.to_json()))
    assert e.count == 2
    assert len(e.events) == 2
    e0 = eptEndpointEvent.from_dict(e.events[0])
    assert e0.node == vpc_node_id
    assert e0.intf_id == "vpc-384"
    assert e0.intf_name == "ag_vpc1"
    assert e0.encap == epg2_encap
    assert e0.pctag == epg2_pctag 
    e1 = eptEndpointEvent.from_dict(e.events[1])
    assert e1.node == vpc_node_id
    assert e1.intf_id == "vpc-384"
    assert e1.intf_name == "ag_vpc1"
    assert e1.encap == epg1_encap
    assert e1.pctag == epg1_pctag 

    # ensure move event was created
    move = eptMove.find(fabric=tfabric, addr=ip)
    assert len(move) == 1
    move = move[0]
    logger.debug(pretty_print(move.to_json()))
    assert move.count == 1
    assert len(move.events) == 1
    src = eptMoveEvent.from_dict(move.events[0]["src"])
    dst = eptMoveEvent.from_dict(move.events[0]["dst"])
    assert src.node == vpc_node_id
    assert src.intf_id == "vpc-384"
    assert src.intf_name == "ag_vpc1"
    assert src.pctag == epg1_pctag
    assert src.encap == epg1_encap
    assert src.rw_mac == mac
    assert src.rw_bd == bd1_vnid
    assert src.epg_name == epg1_name
    assert src.vnid_name == vrf_name
    assert dst.node == vpc_node_id
    assert dst.intf_id == "vpc-384"
    assert dst.intf_name == "ag_vpc1"
    assert dst.pctag == epg2_pctag
    assert dst.encap == epg2_encap
    assert dst.rw_mac == mac
    assert dst.rw_bd == bd2_vnid
    assert dst.epg_name == epg2_name
    assert dst.vnid_name == vrf_name


def test_handle_endpoint_event_vpc_ipv4_move_scenario_1(app, func_prep):
    # trigger an ipv4 move between two bds, same interface with various order of events
    # - ip_event create on node-101
    # - ip_rs_event create on node-101
    # - ip_event create on node-102
    # - ip_rs_event create on node-102
    # - ip_rs_event delete on node-101
    # - ip_event delete on node-101
    # - ip_rs_event delete on node-102
    # - ip_event delete on node-102
    # - ip_rs_event create on node-101 
    # - ip_event create on node-101 with new encap
    # - ip_rs_event create on node-102
    # - ip_event create on node-102 with new encap

    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"

    # vpc-384
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="po2", ts=1.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=1, ts=1.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="po8", ts=1.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=1, ts=1.4)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="deleted", ts=2.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, status="deleted", ts=2.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="deleted", ts=2.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, status="deleted", ts=2.4)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # create on new epg/bd
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=2, intf="po2", ts=3.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=2, ts=3.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=2, intf="po8", ts=3.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=2, ts=3.4)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    validate_ip_state_3()

def test_handle_endpoint_event_vpc_ipv4_move_scenario_2(app, func_prep):
    # trigger an ipv4 move between two bds, same interface with various order of events
    # - ip_event create on node-101
    # - ip_rs_event create on node-101
    # - ip_event create on node-102
    # - ip_rs_event create on node-102
    #
    # - ip_rs_event delete on node-101
    # - ip_rs_event create on node-101 with new encap
    # - ip_event delete on node-101
    # - ip_event create on node-101 with new bd
    #
    # - ip_event delete on node-102
    # - ip_event create on node-102 with new bd
    # - ip_rs_event delete on node-102
    # - ip_rs_event create on node-102 with new encap

    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"

    # vpc-384
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="po2", ts=1.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=1, ts=1.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="po8", ts=1.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=1, ts=1.4)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, status="deleted", ts=2.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=2, ts=2.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="deleted", ts=2.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=2, intf="po2", ts=2.4)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    msg = get_epm_event(102, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="deleted", ts=3.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=2, intf="po8", ts=3.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, status="deleted", ts=3.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=2, ts=3.4)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

def test_handle_endpoint_event_vl_vpc_tunnel_no_move(app, func_prep):
    # trigger learn events from two different tunnels representing same VL device and ensure no
    # move event is triggered

    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"

    # tunnel901/tunnel902 = 10.0.0.90 VL
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="tunnel901", 
            flags=["local", "vpc-attached"],ts=1.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=1, ts=1.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="tunnel902", 
            flags=["local", "vpc-attached"],ts=1.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=1, ts=1.4)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    h = eptHistory.find(fabric=tfabric, addr=ip, node=101)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 2
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert e.remote == 0
    assert e.pctag == epg1_pctag
    assert e.rw_mac == mac
    assert e.rw_bd == bd1_vnid
    assert e.intf_id == "vl-10.0.0.90"
    assert e.intf_name == "vl-10.0.0.90"
    assert e.epg_name == epg1_name
    assert e.vnid_name == vrf_name

    h = eptHistory.find(fabric=tfabric, addr=ip, node=102)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert len(h.events) == 2
    e = eptHistoryEvent.from_dict(h.events[0])
    assert e.status == "created"
    assert e.remote == 0
    assert e.pctag == epg1_pctag
    assert e.rw_mac == mac
    assert e.rw_bd == bd1_vnid
    assert e.intf_id == "vl-10.0.0.90"
    assert e.intf_name == "vl-10.0.0.90"
    assert e.epg_name == epg1_name
    assert e.vnid_name == vrf_name

    endpoint = eptEndpoint.find(fabric=tfabric, addr=ip)
    assert len(endpoint) == 1
    e = endpoint[0]
    logger.debug(pretty_print(e.to_json()))
    assert e.count == 1
    assert len(e.events) == 1
    e0 = eptEndpointEvent.from_dict(e.events[0])
    assert e0.node == vpc_node_id
    assert e0.intf_id == "vl-10.0.0.90"
    assert e0.intf_name == "vl-10.0.0.90"
    assert e0.encap == epg1_encap
    assert e0.pctag == epg1_pctag 
    assert e0.rw_mac == mac
    assert e0.rw_bd == bd1_vnid
    assert e0.epg_name == epg1_name
    assert e0.vnid_name == vrf_name

def test_handle_endpoint_event_local_ipv4_is_offsubnet(app, func_prep):
    # basic check to ensure is_offsubnet is set for local offsubnet address
    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "20.1.1.101"           # subnet 20.1.1.101 belongs to bd2, not bd1
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, bd=1, intf="po2", ts=1.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, bd=1, ts=1.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    h = eptHistory.find(fabric=tfabric, addr=ip, node=101)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert h.is_offsubnet

def test_handle_endpoint_event_xr_ipv4_is_offsubnet(app, func_prep):
    # basic check to ensure is_offsubnet is set for xr offsubnet address
    dut = get_worker()
    ip = "20.1.1.101"           # subnet 20.1.1.101 belongs to bd2, not bd1
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, remote_node=101)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    h = eptHistory.find(fabric=tfabric, addr=ip, node=103)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert h.is_offsubnet

def test_handle_endpoint_event_local_ipv6_is_offsubnet(app, func_prep):
    # basic check to ensure is_offsubnet is set for local offsubnet address
    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "2001:20:1:1::101"     # subnet 2001:20:1:1::/64 belongs to bd2, not bd1
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, bd=1, intf="po2", ts=1.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, bd=1, ts=1.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    h = eptHistory.find(fabric=tfabric, addr=ip, node=101)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert h.is_offsubnet

def test_handle_endpoint_event_xr_ipv6_is_offsubnet(app, func_prep):
    # basic check to ensure is_offsubnet is set for xr offsubnet address
    dut = get_worker()
    ip = "2001:20:1:1::101"     # subnet 2001:20:1:1::/64 belongs to bd2, not bd1
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, remote_node=101)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    h = eptHistory.find(fabric=tfabric, addr=ip, node=103)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert h.is_offsubnet

def test_handle_endpoint_event_skip_offsubnet_check_for_static(app, func_prep):
    # create an offsubnet endpoint for static vip and ensure check is skipped
    dut = get_worker()
    ip = "8.8.8.8"
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, remote_node=101, flags=["static"])
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    h = eptHistory.find(fabric=tfabric, addr=ip, node=103)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    # technically offsubnet but vip flag in endpoint skips check
    assert not h.is_offsubnet

def test_handle_endpoint_event_stale_scenario_1(app, func_prep):
    # basic stale event:
    # - ip_event create on node-103
    # - ip_rs_event create on node-103
    # - XR ip_event create on node-104
    # ----> move to node-101
    # - ip_event create on node-101
    # - ip_rs_event create on node-101
    # - ip_event delete on node-103
    # - ip_rs_event delete on node-103
    # - ip_event XR create on node-103 with bounce
    # ----> simulate wait for bounce to expire
    # - ip_event modify on node-103 remove bounce flag

    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"

    # initial state on node-103 and node-104
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="eth1/1", ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=1, ts=1.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(104, ip, wt=WORK_TYPE.EPM_IP_EVENT, remote_node=103, ts=1.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    # move to node-101, with bounce on node-103
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="eth1/1", ts=2.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=1, ts=2.1)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, status="deleted", ts=2.2)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, status="deleted", ts=2.3)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, remote_node=101, ts=2.4, flags=["bounce"])
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # at this point, no device should have is_stale set
    h = eptHistory.find(fabric=tfabric, addr=ip)
    assert len(h)==3
    for n in h:
        assert not n.is_stale

    # modify node-103, removing bounce flag
    msg = get_epm_event(103, ip, wt=WORK_TYPE.EPM_IP_EVENT, remote_node=101, status="modified", 
            ts=603, flags=["ip"])
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # ensure is_stale is set on node-104 only
    h = eptHistory.find(fabric=tfabric, addr=ip, node=104)
    assert len(h)==1
    h = h[0]
    logger.debug(pretty_print(h.to_json()))
    assert h.is_stale


def test_handle_endpoint_invalid_old_last_local(app, func_prep):
    # this test we want to create two valid local entries.  First, on node-101 and then on node-102.
    # Next, we invalidate the local entry on node-102 without an update on node-101. We need to 
    # ensure that we don't reuse node-101 as best local and instead return a delete as the last 
    # local.
    
    dut = get_worker()
    mac = "00:00:01:02:03:04"
    ip = "10.1.1.101"

    # initial local learn
    msg = get_epm_event(101, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="eth1/1", ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(101, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=1, ts=1.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, ip, wt=WORK_TYPE.EPM_IP_EVENT, epg=1, intf="eth1/1", ts=2.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)
    msg = get_epm_event(102, mac, ip=ip, wt=WORK_TYPE.EPM_RS_IP_EVENT, epg=1, ts=2.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # at this point eptEndpoint should have 102 as current local
    e = eptEndpoint.find(fabric=tfabric, addr=ip)
    assert len(e)==1
    assert len(e[0].events)==2
    e0 = eptEndpointEvent.from_dict(e[0].events[0])
    assert e0.node == 102

    # now we invalidate leaf-102 as the local and eptEndpoint should have last local as deleted,
    # not leaf-101
    msg = get_epm_event(102, ip, status="deleted", ts=3.0)
    dut.set_msg_worker_fabric(msg)
    dut.handle_endpoint_event(msg)

    # at this point eptEndpoint should have 102 as current local
    e = eptEndpoint.find(fabric=tfabric, addr=ip)
    assert len(e)==1
    assert len(e[0].events)==3
    e0 = eptEndpointEvent.from_dict(e[0].events[0])
    assert e0.node == 0
    assert e0.status == "deleted"

