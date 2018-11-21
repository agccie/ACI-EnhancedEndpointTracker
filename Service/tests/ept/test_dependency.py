
import logging
import pytest
import time

from app.models.aci.fabric import Fabric

from app.models.aci.ept.ept_epg import eptEpg
from app.models.aci.ept.ept_node import eptNode
from app.models.aci.ept.ept_subnet import eptSubnet
from app.models.aci.ept.ept_tunnel import eptTunnel
from app.models.aci.ept.ept_vnid import eptVnid
from app.models.aci.ept.mo_dependency_map import dependency_map as dmap

from app.models.aci.mo.fvCtx import fvCtx
from app.models.aci.mo.fvBD import fvBD
from app.models.aci.mo.fvSvcBD import fvSvcBD
from app.models.aci.mo.l3extExtEncapAllocator import l3extExtEncapAllocator
from app.models.aci.mo.l3extInstP import l3extInstP
from app.models.aci.mo.l3extOut import l3extOut
from app.models.aci.mo.l3extRsEctx import l3extRsEctx
from app.models.aci.mo.fvAEPg import fvAEPg
from app.models.aci.mo.fvRsBd import fvRsBd
from app.models.aci.mo.vnsEPpInfo import vnsEPpInfo
from app.models.aci.mo.vnsRsEPpInfoToBD import vnsRsEPpInfoToBD
from app.models.aci.mo.mgmtInB import mgmtInB
from app.models.aci.mo.mgmtRsMgmtBD import mgmtRsMgmtBD
from app.models.aci.mo.fvSubnet import fvSubnet
from app.models.aci.mo.fvIpAttr import fvIpAttr
from app.models.aci.mo.vnsLIfCtx import vnsLIfCtx
from app.models.aci.mo.vnsRsLIfCtxToBD import vnsRsLIfCtxToBD
from app.models.aci.mo.tunnelIf import tunnelIf

# module level logging
logger = logging.getLogger(__name__)

tfabric = "fab1"

@pytest.fixture(scope="module")
def app(request):
    # module level setup 

    from app import create_app
    app = create_app("config.py")

    # teardown called after all tests in session have completed
    def teardown(): pass
    request.addfinalizer(teardown)

    logger.debug("(%s) module level app setup completed", __name__)
    return app

@pytest.fixture(scope="function")
def func_prep(request, app):
    # perform proper proper prep/cleanup
    # will delete all mo objects we're using as part of dependency testing

    logger.debug("%s %s setup", "."*80, __name__)
    assert Fabric.load(fabric=tfabric).save()


    def teardown(): 
        logger.debug("%s %s teardown", ":"*80, __name__)
        eptEpg.delete(_filters={})
        eptVnid.delete(_filters={})
        eptSubnet.delete(_filters={})
        eptTunnel.delete(_filters={})
        fvCtx.delete(_filters={})
        fvBD.delete(_filters={})
        fvSvcBD.delete(_filters={})
        fvAEPg.delete(_filters={})
        fvRsBd.delete(_filters={})
        vnsEPpInfo.delete(_filters={})
        vnsRsEPpInfoToBD.delete(_filters={})
        vnsLIfCtx.delete(_filters={})
        vnsRsLIfCtxToBD.delete(_filters={})
        mgmtInB.delete(_filters={})
        mgmtRsMgmtBD.delete(_filters={})
        l3extInstP.delete(_filters={})
        l3extExtEncapAllocator.delete(_filters={})
        l3extOut.delete(_filters={})
        l3extRsEctx.delete(_filters={})
        fvSubnet.delete(_filters={})
        fvIpAttr.delete(_filters={})
        tunnelIf.delete(_filters={})
        
    request.addfinalizer(teardown)
    return

def get_create_event(attr, ts=0xefffffff):
    # create an event based on MO that can be provided to DependencyNode.sync_event
    event = {"_ts": ts, "status": "created"}
    for a in attr:
        event[a] = attr[a]
    return event

def get_update_event(attr, ts=0xf0000001):
    # update an event based on MO that can be provided to DependencyNode.sync_event
    event = {"_ts": ts, "status": "modified"}
    for a in attr:
        event[a] = attr[a]
    return event

def get_delete_event(attr, ts=0xf0000001):
    # delete an event based on MO that can be provided to DependencyNode.sync_event
    return {"_ts": ts, "status": "deleted", "dn":attr["dn"]}

def test_dependency_sync_new_bd(app, func_prep):
    # simulate create event for a new bd and no dependents, should result in creation of entry
    # in vnid table
    dn = "uni/tn-ag/BD-bd1"
    vrf = 1
    vnid = 2
    pctag = 3
    updates = dmap["fvBD"].sync_event(tfabric, get_create_event({
            "dn": dn,
            "pcTag": pctag,
            "scope": vrf,
            "seg": vnid
        }))
    assert len(updates) == 1
    assert updates[0]._classname == eptVnid._classname
    assert updates[0].name == dn
    insert = eptVnid.load(fabric=tfabric, name=dn)
    assert insert.exists()
    assert insert.vnid == vnid
    assert insert.vrf == vrf
    assert insert.pctag == pctag

def test_dependency_sync_new_epg_then_new_bd(app, func_prep):
    # simulate create event for a new fvAEPg followed by new bd and ensure that out-of-order events
    # are handled correctly.  Also ensure that, prior to fvBD create, eptEpg object exists with 
    # bd value of 0 indicating unresolved connection
    
    vrf = 1
    bd_dn = "uni/tn-ag/BD-bd1"
    bd_vnid = 2
    bd_pctag = 4
    epg_dn = "uni/tn-ap/ap-ap1/epg-e1"
    epg_pctag = 3
    logger.debug("***** step 1 - sync fvAEPg")
    updates = dmap["fvAEPg"].sync_event(tfabric, get_create_event({
            "dn": epg_dn,
            "pcTag": epg_pctag,
            "scope": vrf,
            "isAttrBasedEPg": "no"
        }))
    assert len(updates) == 1
    assert updates[0]._classname == eptEpg._classname
    assert updates[0].name == epg_dn

    epg_insert = eptEpg.find(fabric=tfabric, name=epg_dn)
    assert len(epg_insert)==1
    assert epg_insert[0].exists()
    assert epg_insert[0].bd == 0

    # create fvRsBd binding to a non-existing BD which is supported (or to simulate BD deleted and
    # the created)
    logger.debug("***** step 2 - sync fvRsBd")
    updates = dmap["fvRsBd"].sync_event(tfabric, get_create_event({
            "dn": "%s/rsbd" % epg_dn,
            "tDn": bd_dn,
        }))
    assert len(updates) == 0    # no ept object affected after adding fvRsBd object at this point

    logger.debug("***** step 3 - sync fvBD")
    updates = dmap["fvBD"].sync_event(tfabric, get_create_event({
            "dn": bd_dn,
            "pcTag": bd_pctag,
            "scope": vrf,
            "seg": bd_vnid
        }))
    assert len(updates) == 2    # eptVnid and eptEpg updated
    assert updates[0]._classname == eptVnid._classname
    assert updates[0].name == bd_dn
    assert updates[1]._classname == eptEpg._classname
    assert updates[1].name == epg_dn
    epg_insert[0].reload()
    assert epg_insert[0].bd == bd_vnid

def test_dependency_bd_update_propogated_to_multiple_subnets(app, func_prep):
    # simulate update event to existing BD (changing vnid) and ensure change is propogated to child
    # fvSubnet along with fvSubnet anchored on fvAEPg and vnsLIfCtx
    # use this same test to simulate creation of objects and connectors in arbitrary order

    # create two epgs, each with fvSubnet
    vrf = 1
    bd_dn = "uni/tn-ag/BD-bd1"
    bd_vnid = 2
    bd_pctag = 3
    epg_pctag = 4
    epg_dn = "uni/tn-ap/ap-ap1/epg-e"
    vns_dn = "uni/tn-ag/ldevCtx-c-c1-g-sg1-n-N1/lIfCtx-c-provider"
    logger.debug("***** step 1 - initial build")
    dmap["fvAEPg"].sync_event(tfabric, get_create_event({
            "dn": "%s1" % epg_dn,
            "pcTag": epg_pctag,
            "scope": vrf,
            "isAttrBasedEPg": "no"
    }))
    dmap["fvAEPg"].sync_event(tfabric, get_create_event({
            "dn": "%s2" % epg_dn,
            "pcTag": epg_pctag,
            "scope": vrf,
            "isAttrBasedEPg": "yes"
    }))
    dmap["fvSubnet"].sync_event(tfabric, get_create_event({
            "dn": "%s1/subnet-[1.1.1.1/24]" % epg_dn,
            "ip": "1.1.1.1/24"
    }))
    dmap["fvIpAttr"].sync_event(tfabric, get_create_event({
            "dn": "%s2/crtrn/ipattr-0" % epg_dn,
            "ip": "2.2.2.2/24",
            "usefvSubnet": "no",
    }))
    dmap["vnsLIfCtx"].sync_event(tfabric, get_create_event({
            "dn": vns_dn,
    }))
    dmap["fvSubnet"].sync_event(tfabric, get_create_event({
            "dn": "%s/subnet-[3.3.3.3/24]" % vns_dn,
            "ip": "3.3.3.3/24"
    }))
    dmap["fvBD"].sync_event(tfabric, get_create_event({
            "dn": bd_dn,
            "pcTag": bd_pctag,
            "scope": vrf,
            "seg": bd_vnid
    }))
    dmap["fvSubnet"].sync_event(tfabric, get_create_event({
            "dn": "%s/subnet-[4.4.4.4/24]" % bd_dn,
            "ip": "4.4.4.4/24"
    }))
    dmap["fvSubnet"].sync_event(tfabric, get_create_event({
            "dn": "%s/subnet-[5.5.5.5/24]" % bd_dn,
            "ip": "5.5.5.5/24"
    }))

    # connect epgs to BD
    dmap["fvRsBd"].sync_event(tfabric, get_create_event({
            "dn": "%s1/rsbd" % epg_dn,
            "tDn": bd_dn,
    }))
    dmap["fvRsBd"].sync_event(tfabric, get_create_event({
            "dn": "%s2/rsbd" % epg_dn,
            "tDn": bd_dn,
    }))
    dmap["vnsRsLIfCtxToBD"].sync_event(tfabric, get_create_event({
            "dn": "%s/rsLIfCtxToBD" % vns_dn,
            "tDn": bd_dn,
    }))

    # ensure that base objects are created and have correct bd vnid
    bd_dut = eptVnid.load(fabric=tfabric, name=bd_dn)
    assert bd_dut.exists()
    assert bd_dut.vnid == bd_vnid
    subnet_dn_list = [
        "%s1/subnet-[1.1.1.1/24]" % epg_dn,
        "%s2/crtrn/ipattr-0" % epg_dn,
        "%s/subnet-[3.3.3.3/24]" % vns_dn,
        "%s/subnet-[4.4.4.4/24]" % bd_dn,
        "%s/subnet-[5.5.5.5/24]" % bd_dn,
    ]
    epg_dn_list = [
        "%s1" % epg_dn,
        "%s2" % epg_dn,
    ]
    for sdn in subnet_dn_list:
        logger.debug("verifying subnet: %s", sdn)
        subnet = eptSubnet.load(fabric=tfabric, name=sdn)
        assert subnet.exists()
        assert subnet.bd == bd_vnid
    for edn in epg_dn_list:
        logger.debug("verifying epg: %s", edn)
        epg = eptEpg.find(fabric=tfabric, name=edn)
        assert len(epg) == 1 
        assert epg[0].bd == bd_vnid

    # change bd vnid and ensure change is propogated to all approproate objects
    logger.debug("***** step 2 - change bd vnid")
    bd_vnid2 = 0xffff
    updates = dmap["fvBD"].sync_event(tfabric, get_update_event({
            "dn": bd_dn,
            "seg": bd_vnid2
    }))

    # ensure all vnids are updated
    bd_dut = eptVnid.load(fabric=tfabric, name=bd_dn)
    assert bd_dut.exists()
    assert bd_dut.vnid == bd_vnid2
    subnet_dn_list = [
        "%s1/subnet-[1.1.1.1/24]" % epg_dn,
        "%s2/crtrn/ipattr-0" % epg_dn,
        "%s/subnet-[3.3.3.3/24]" % vns_dn,
        "%s/subnet-[4.4.4.4/24]" % bd_dn,
        "%s/subnet-[5.5.5.5/24]" % bd_dn,
    ]
    epg_dn_list = [
        "%s1" % epg_dn,
        "%s2" % epg_dn,
    ]
    for sdn in subnet_dn_list:
        logger.debug("verifying subnet: %s", sdn)
        subnet = eptSubnet.load(fabric=tfabric, name=sdn)
        assert subnet.exists()
        assert subnet.bd == bd_vnid2
    for edn in epg_dn_list:
        logger.debug("verifying epg: %s", edn)
        epg = eptEpg.find(fabric=tfabric, name=edn)
        assert len(epg) == 1 
        assert epg[0].bd == bd_vnid2

def test_dependency_delete_bd_and_ensure_epg_vnid_reset(app, func_prep):
    # create existing ept and mo for BD, fvRsBD, and epg.  Ensure eptEpg bd is set to correct vnid 
    # and then delete fvBD and ensure eptEpg bd is set to zero
   
    vrf = 1
    bd_dn = "uni/tn-ag/BD-bd1"
    bd_vnid = 2
    bd_pctag = 3
    epg_pctag = 4
    epg_dn = "uni/tn-ap/ap-ap1/epg-e1"

    dmap["fvAEPg"].sync_event(tfabric, get_create_event({
        "dn": epg_dn,
        "pcTag": epg_pctag,
        "scope": vrf,
        "isAttrBasedEPg": "no",
    }))
    dmap["fvBD"].sync_event(tfabric, get_create_event({
        "dn": bd_dn,
        "pcTag": bd_pctag,
        "scope": vrf,
        "seg": bd_vnid
    }))
    dmap["fvSubnet"].sync_event(tfabric, get_create_event({
        "dn": "%s/subnet-[1.1.1.1/24]" % epg_dn,
        "ip": "1.1.1.1/24"
    }))
    dmap["fvRsBd"].sync_event(tfabric, get_create_event({
        "dn": "%s/rsbd" % epg_dn,
        "tDn": bd_dn,
    }))

    bd = eptVnid.load(fabric=tfabric, name=bd_dn)
    assert bd.exists() and bd.vnid == bd_vnid
    epg = eptEpg.load(fabric=tfabric, name=epg_dn)
    assert epg.exists() and epg.bd == bd_vnid
    subnet = eptSubnet.load(fabric=tfabric, name="%s/subnet-[1.1.1.1/24]"%epg_dn)
    assert subnet.exists() and subnet.bd == bd_vnid

    # delete bd and ensure epg and subnet bd's are set to 0
    logger.debug("***** step 2 - delete bd")
    updates = dmap["fvBD"].sync_event(tfabric, get_delete_event({"dn":bd_dn}))
    assert len(updates) == 3

    bd = eptVnid.load(fabric=tfabric, name=bd_dn)
    assert not bd.exists()
    epg = eptEpg.load(fabric=tfabric, name=epg_dn)
    assert epg.exists() and epg.bd == 0
    subnet = eptSubnet.load(fabric=tfabric, name="%s/subnet-[1.1.1.1/24]"%epg_dn)
    assert subnet.exists() and subnet.bd == 0


def test_dependency_delete_fvrsbd_and_ensure_epg_vnid_reset(app, func_prep):
    # create existing ept and mo for BD, fvRsBD, and epg.  Ensure eptEpg bd is set to correct vnid 
    # and then delete fvRsBD and ensure eptEpg bd is set to zero
    #
    vrf = 1
    bd_dn = "uni/tn-ag/BD-bd1"
    bd_vnid = 2
    bd_pctag = 3
    epg_pctag = 4
    epg_dn = "uni/tn-ap/ap-ap1/epg-e1"

    dmap["fvAEPg"].sync_event(tfabric, get_create_event({
        "dn": epg_dn,
        "pcTag": epg_pctag,
        "scope": vrf,
        "isAttrBasedEPg": "no",
    }))
    dmap["fvBD"].sync_event(tfabric, get_create_event({
        "dn": bd_dn,
        "pcTag": bd_pctag,
        "scope": vrf,
        "seg": bd_vnid
    }))
    dmap["fvSubnet"].sync_event(tfabric, get_create_event({
        "dn": "%s/subnet-[1.1.1.1/24]" % epg_dn,
        "ip": "1.1.1.1/24"
    }))
    dmap["fvRsBd"].sync_event(tfabric, get_create_event({
        "dn": "%s/rsbd" % epg_dn,
        "tDn": bd_dn,
    }))

    bd = eptVnid.load(fabric=tfabric, name=bd_dn)
    assert bd.exists() and bd.vnid == bd_vnid
    epg = eptEpg.load(fabric=tfabric, name=epg_dn)
    assert epg.exists() and epg.bd == bd_vnid
    subnet = eptSubnet.load(fabric=tfabric, name="%s/subnet-[1.1.1.1/24]"%epg_dn)
    assert subnet.exists() and subnet.bd == bd_vnid
    # ensure fvRsBd mo exists 
    assert fvRsBd.load(fabric=tfabric, dn="%s/rsbd" % epg_dn).exists()

    # delete bd and ensure epg and subnet bd's are set to 0
    logger.debug("***** step 2 - delete fvRsBd")
    updates = dmap["fvRsBd"].sync_event(tfabric, get_delete_event({"dn":"%s/rsbd" % epg_dn}))
    assert len(updates) == 2

    bd = eptVnid.load(fabric=tfabric, name=bd_dn)
    assert bd.exists() and bd.vnid == bd_vnid       # no change to original bd
    epg = eptEpg.load(fabric=tfabric, name=epg_dn)
    assert epg.exists() and epg.bd == 0
    subnet = eptSubnet.load(fabric=tfabric, name="%s/subnet-[1.1.1.1/24]"%epg_dn)
    assert subnet.exists() and subnet.bd == 0
    # ensure fvRsBd mo does not exists 
    assert not fvRsBd.load(fabric=tfabric, dn="%s/rsbd" % epg_dn).exists()

def test_dependency_delete_epg_and_ensure_ept_epg_is_deleted(app, func_prep):
    # simple test to ensure eptEpg objects are deleted when mo.fvAEPg objects are deleted
    vrf = 1
    epg_pctag = 4
    epg_dn = "uni/tn-ap/ap-ap1/epg-e1"

    updates = dmap["fvAEPg"].sync_event(tfabric, get_create_event({
        "dn": epg_dn,
        "pcTag": epg_pctag,
        "scope": vrf,
        "isAttrBasedEPg": "no",
    }))
    assert len(updates) == 1
    assert eptEpg.load(fabric=tfabric, name=epg_dn).exists()
    assert fvAEPg.load(fabric=tfabric, dn=epg_dn).exists()

    updates = dmap["fvAEPg"].sync_event(tfabric, get_delete_event({"dn":epg_dn}))
    assert len(updates) == 1
    assert not eptEpg.load(fabric=tfabric, name=epg_dn).exists()
    assert not fvAEPg.load(fabric=tfabric, dn=epg_dn).exists()

def test_dependency_validate_l3ext_encap_vrf_is_mapped(app, func_prep):
    # create vrf, l3out, and l3extExtEncapAllocator and ensure it get the vrf pushed

    vrf = 1
    vrf_pctag = 101
    vrf_dn = "uni/tn-ag/ctx-v1"
    l3out_dn = "uni/tn-ag/out-out1"
    ext_encap = "vlan-122"
    ext_vnid = 5
    dmap["fvCtx"].sync_event(tfabric, get_create_event({
        "dn": vrf_dn,
        "pcTag": vrf_pctag,
        "scope": vrf,
    }))
    dmap["l3extOut"].sync_event(tfabric, get_create_event({"dn": l3out_dn}))
    dmap["l3extRsEctx"].sync_event(tfabric, get_create_event({
        "dn": "%s/rsectx" % l3out_dn,
        "tDn": vrf_dn
    }))
    logger.debug("***** step 2 - create l3extEtEncapAllocator")
    dmap["l3extExtEncapAllocator"].sync_event(tfabric, get_create_event({
        "dn": "%s/encap-[%s]" % (l3out_dn, ext_encap),
        "encap": ext_encap,
        "extEncap": "vxlan-%s" % ext_vnid,
    }))

    assert fvCtx.load(fabric=tfabric, dn=vrf_dn).exists()
    assert l3extOut.load(fabric=tfabric, dn=l3out_dn).exists()
    assert l3extRsEctx.load(fabric=tfabric, dn="%s/rsectx" % l3out_dn).exists()
    dut1 = l3extExtEncapAllocator.load(fabric=tfabric, dn="%s/encap-[%s]" % (l3out_dn, ext_encap))
    assert dut1.exists()
    dut2 = eptVnid.load(fabric=tfabric, name=dut1.dn)
    assert dut2.exists()
    assert dut2.vrf == vrf
    assert dut2.encap == ext_encap
    assert dut2.pctag == 0
    assert dut2.vnid == ext_vnid
   
def test_dependency_tunnel_if_callback(app, func_prep):
    # validate

    # create a dummy node and ensure that tunnel event sync updates eptTunnel with correct remote
    # node value
    assert eptNode.load(fabric=tfabric,node=199,pod_id=1,role="leaf",addr="10.0.0.199").save()

    dmap["tunnelIf"].sync_event(tfabric, get_create_event({
        "dn": "topology/pod-1/node-101/sys/tunnel-[tunnel199]",
        "id": "tunnel199",
        "dest": "10.0.0.199/32",
        "src": "10.0.0.101",
        "operSt": "up",
        "tType": "ivxlan",
        "type": "physical",
        "status": "created",
    }))

    tunnel = eptTunnel.find(fabric=tfabric, node=101, intf="tunnel199")
    assert len(tunnel)==1
    tunnel = tunnel[0]
    assert tunnel.remote == 199
