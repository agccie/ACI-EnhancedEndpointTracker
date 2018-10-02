

import logging
import pytest
import time

from app.models.aci.fabric import Fabric

from app.models.aci.ept.ept_epg import eptEpg
from app.models.aci.ept.ept_subnet import eptSubnet
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

# module level logging
logger = logging.getLogger(__name__)

tfabric = "fab1"

@pytest.fixture(scope="module")
def app(request):
    # module level setup executed before any 'user' test in current file

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
        
    request.addfinalizer(teardown)
    return

def get_create_event(mo, ts=0xefffffff):
    # create an event based on MO that can be provided to DependencyNode.sync_event
    event = {"_ts": ts, "status": "created"}
    for a in mo._attributes:
        event[a] = getattr(mo, a)
    return event

def test_dependency_sync_new_bd(app, func_prep):
    # simulate create event for a new bd and no dependents, should result in creation of entry
    # in vnid table
    dn = "uni/tn-ag/BD-bd1"
    vrf = 2850818
    vnid = 15892495
    pctag = 16386
    mo = fvBD.load(fabric=tfabric, pcTag=pctag, scope=vrf, seg=vnid)
    assert mo.save()
    dmap["fvBD"].sync_event(tfabric, get_create_event(mo))


