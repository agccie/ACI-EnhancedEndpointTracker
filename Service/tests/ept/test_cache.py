
import logging
import pytest
import time

from app.models.aci.fabric import Fabric

from app.models.aci.ept.ept_cache import eptCache
from app.models.aci.ept.ept_cache import hitCache
from app.models.aci.ept.ept_cache import hitCacheNotFound
from app.models.aci.ept.ept_cache import offsubnetCachedObject
from app.models.aci.ept.ept_epg import eptEpg
from app.models.aci.ept.ept_node import eptNode
from app.models.aci.ept.ept_subnet import eptSubnet
from app.models.aci.ept.ept_tunnel import eptTunnel
from app.models.aci.ept.ept_vnid import eptVnid
from app.models.aci.ept.ept_vpc import eptVpc
from app.models.aci.ept.common import get_ip_prefix

# module level logging
logger = logging.getLogger(__name__)

tfabric = "fab1"

@pytest.fixture(scope="module")
def app(request, app):
    # module level setup
    app.config["LOGIN_ENABLED"] = False

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
        eptNode.delete(_filters={})
        eptVpc.delete(_filters={})
        eptTunnel.delete(_filters={})
        
    request.addfinalizer(teardown)
    return

class dummyHitObject(object):
    # object with name and val attributes
    def __init__(self, name, val):
        self.name = name
        self.val = val

def get_test_cache(max_cache_size=None):
    c = eptCache(fabric=tfabric)
    if max_cache_size is not None:
        c.max_cache_size = max_cache_size
    return c

def test_hit_cache_general_key_wrap(app, func_prep):
    # ensure that cache is wrapping keys, most recent at top of cache and values exceeding length
    # removed.
    h_cache = hitCache(5)
    h_cache.push("key1", "val1")
    assert h_cache.head.key == "key1" and h_cache.head.val == "val1"
    assert h_cache.get_size() == 1
    h_cache.push("key2", "val2")
    h_cache.push("key3", "val3")
    h_cache.push("key4", "val4")
    h_cache.push("key5", "val5")
    h_cache.push("key6", "val6")
    assert h_cache.get_size() == 5
    assert h_cache.head.key == "key6" and h_cache.head.val == "val6"
    assert h_cache.tail.key == "key2" and h_cache.tail.val == "val2"
    
    # search should move key to list head (does not alter tail)
    assert h_cache.search("key4") == "val4"
    assert h_cache.head.key == "key4"
    assert h_cache.tail.key == "key2"

    # remove everything from cache and ensure no keys is still fine
    h_cache.remove("key2")
    assert h_cache.tail.key == "key3"
    assert h_cache.get_size() == 4
    h_cache.remove("key3")
    assert h_cache.tail.key == "key5"
    assert h_cache.get_size() == 3
    h_cache.remove("key4")
    assert h_cache.head.key == "key6"
    assert h_cache.get_size() == 2
    h_cache.remove("key5")
    assert h_cache.head.key == "key6"
    assert h_cache.tail.key == "key6"
    assert h_cache.get_size() ==1
    h_cache.remove("key6")
    assert h_cache.head == None
    assert h_cache.tail == None
    assert h_cache.get_size() == 0

def test_hit_cache_general_name_and_none_lookup(app, func_prep):
    # ensure that objects added to cache with name attribute are correctly added/removed from hit
    # cache. This function will also verify that none_hash is updating when None values are added

    h_cache = hitCache(5)
    h_cache.push("key1", dummyHitObject("name1","val1"))
    assert isinstance(h_cache.search("name1", name=True), dummyHitObject)
    assert "name1" in h_cache.name_hash

    h_cache.push("key2", None)
    assert h_cache.get_size() == 2
    assert "key2" in h_cache.none_hash

    # add mix of None, single dummyHitObject, and list of dummyHitObjects
    h_cache.push("key3", dummyHitObject("name3", "val3"))
    h_cache.push("key4", [
        dummyHitObject("name4", "val4"), 
        dummyHitObject("name5", "val5"),
        dummyHitObject("name6", "val6"),
        dummyHitObject("name7", "val7"),
    ])
    h_cache.push("key5", None)

    logger.debug("h_cache keys: %s", h_cache.key_hash.keys())
    logger.debug("h_cache none_keys: %s", h_cache.none_hash.keys())
    logger.debug("h_cache names: %s", h_cache.name_hash.keys())

    assert h_cache.get_size() == 5
    assert len(h_cache.name_hash) == 6      # each of the name objects adds entry to name_hash
    assert len(h_cache.none_hash) == 2      # each None object added to none_hash
    assert "name6" in h_cache.name_hash
    assert "name1" in h_cache.name_hash

    # remove one key should also remove all entries in none_hash
    h_cache.remove("key1")
    assert len(h_cache.none_hash) == 0
    assert h_cache.get_size() == 2          # removed key1, key2, and key5
    assert isinstance(h_cache.search("key1"), hitCacheNotFound)
    assert isinstance(h_cache.search("key2"), hitCacheNotFound)
    assert isinstance(h_cache.search("key5"), hitCacheNotFound)

    # remove one of name4-7 should remove key4 and all name references
    h_cache.remove("name6", name=True)
    assert isinstance(h_cache.search("key4"), hitCacheNotFound)
    assert "name4" not in h_cache.name_hash
    assert "name5" not in h_cache.name_hash
    assert "name6" not in h_cache.name_hash
    assert "name7" not in h_cache.name_hash
    assert h_cache.get_size() == 1

    # only node left at this point is key3
    assert h_cache.search("key3").val == "val3"

    # let's add another list of dummyHit and ensure removing key removes all name references
    h_cache.push("key4", [
        dummyHitObject("name4", "val4"), 
        dummyHitObject("name5", "val5"),
        dummyHitObject("name6", "val6"),
        dummyHitObject("name7", "val7"),
    ])
    assert "name6" in h_cache.name_hash
    assert h_cache.get_size() == 2
    assert "key4" in h_cache.key_hash

    h_cache.remove("key4")
    assert "name4" not in h_cache.name_hash
    assert "name5" not in h_cache.name_hash
    assert "name6" not in h_cache.name_hash
    assert "name7" not in h_cache.name_hash
    assert h_cache.get_size() == 1


def test_get_peer_node_lookup(app, func_prep):
    # add eptNode object and ensure cache returns peer value if found, and 0 if not present
    # trigger flush and ensure value is no longer found within cache
    cache = get_test_cache()
    node = 101
    peer = 102
    name = "node1"
    keystr = cache.get_key_str(node=node)
    assert eptNode.load(fabric=tfabric, node=node, name=name, peer=peer, pod_id=1, role="leaf").save()
    assert cache.get_peer_node(node) == peer
    assert isinstance(cache.node_cache.search(keystr), eptNode)
    assert cache.get_peer_node(12345) == 0
    cache.handle_flush(eptNode._classname)
    assert isinstance(cache.node_cache.search(keystr), hitCacheNotFound)
    assert cache.get_peer_node(node) == peer
    assert isinstance(cache.node_cache.search(keystr), eptNode)

def test_get_tunnel_remote_lookup(app, func_prep):
    # add eptTunnel object and ensure cache returns remote node if found, else 0
    # trigger flush and ensure value is no longer found within cache but next lookup adds it
    cache = get_test_cache()
    intf = "tunnel17"
    node = 101
    remote = 102
    keystr = cache.get_key_str(node=node, intf=intf)
    assert eptTunnel(fabric=tfabric, node=node, intf=intf, remote=remote).save()
    assert cache.get_tunnel_remote(node, intf) == remote
    assert isinstance(cache.tunnel_cache.search(keystr), eptTunnel)
    assert cache.get_tunnel_remote(node, "tunnel891") == 0
    cache.handle_flush(eptTunnel._classname)
    assert isinstance(cache.tunnel_cache.search(keystr), hitCacheNotFound)
    assert cache.get_tunnel_remote(node, intf) == remote
    assert isinstance(cache.tunnel_cache.search(keystr), eptTunnel)

def test_get_pc_vpc_id_lookup(app, func_prep):
    # add eptVpc object and ensure cache returns vpc id if found, else 0
    # trigger flush for single name and ensure only that name is removed
    # trigger flush for whole collection and ensure entire collection is flushed
    cache = get_test_cache()
    intf = "po17"
    vpc = 366
    node = 101
    name = "pc-vpc-1"
    keystr = cache.get_key_str(node=node, intf=intf)
    assert eptVpc.load(fabric=tfabric, node=node, intf=intf, vpc=vpc, name=name).save()
    assert eptVpc.load(fabric=tfabric, node=node, intf="po18", vpc=367, name="pc-vpc-2").save()
    assert eptVpc.load(fabric=tfabric, node=node, intf="po19", vpc=368, name="pc-vpc-3").save()
    assert eptVpc.load(fabric=tfabric, node=node, intf="po20", vpc=369, name="pc-vpc-4").save()
    assert cache.get_pc_vpc_id(node, intf) == vpc
    # trigger a hit for the other names so they are added to the cache
    cache.get_pc_vpc_id(node, "po18") == 367
    cache.get_pc_vpc_id(node, "po19") == 368
    cache.get_pc_vpc_id(node, "po20") == 369
    assert cache.vpc_cache.get_size() == 4
    assert isinstance(cache.vpc_cache.search(keystr), eptVpc)
    logger.debug(cache.vpc_cache.search(keystr))
    logger.debug(cache.vpc_cache.name_hash.keys())
    cache.handle_flush(eptVpc._classname, name=name)
    logger.debug("name_hash after name flush: %s", cache.vpc_cache.name_hash.keys())
    assert isinstance(cache.vpc_cache.search(keystr), hitCacheNotFound)
    assert cache.vpc_cache.get_size() == 3
    cache.handle_flush(eptVpc._classname)
    assert cache.vpc_cache.get_size() == 0

def test_get_epg_name_lookup(app, func_prep):
    # add eptEpg object and ensure cache returns epg name if found else empty string
    # trigger flush for single name and ensure only that name is removed
    # trigger flush for whole collection and ensure entire collection is flushed
    cache = get_test_cache()
    name = "epg1"
    vrf = 1
    pctag = 32768
    bd = 2
    keystr = cache.get_key_str(vrf=vrf, pctag=pctag)
    assert eptEpg.load(fabric=tfabric, vrf=vrf, pctag=pctag, bd=bd, name=name).save()
    assert eptEpg.load(fabric=tfabric, vrf=vrf, pctag=2, bd=bd, name="epg2").save()
    assert eptEpg.load(fabric=tfabric, vrf=vrf, pctag=3, bd=3, name="epg3").save()
    assert eptEpg.load(fabric=tfabric, vrf=vrf, pctag=4, bd=4, name="epg4").save()
    assert eptEpg.load(fabric=tfabric, vrf=vrf, pctag=5, bd=5, name="epg5").save()
    assert cache.get_epg_name(vrf, pctag) == name
    assert cache.get_epg_name(vrf, 2) == "epg2"
    assert cache.get_epg_name(vrf, 3) == "epg3"
    assert cache.get_epg_name(vrf, 4) == "epg4"
    assert cache.get_epg_name(vrf, 5) == "epg5"
    assert cache.get_epg_name(vrf, 5, return_object=True).bd == 5
    assert cache.epg_cache.get_size() == 5
    cache.handle_flush(eptEpg._classname, name=name)
    assert cache.epg_cache.get_size() == 4
    assert name not in cache.epg_cache.key_hash
    assert isinstance(cache.epg_cache.search(keystr), hitCacheNotFound)
    cache.handle_flush(eptEpg._classname)
    assert cache.epg_cache.get_size() == 0

def test_vnid_name_lookup(app, func_prep):
    # create an entry in eptVnid and ensure that first lookup returns results and adds to cache
    # ensure second lookup finds entry in cache.  Perform lookup for unknown vnid and ensure empty
    # string is returned.  perform flush for name and ensure value is no longer found
    cache = get_test_cache()
    name = "name1"
    vnid = 1
    assert eptVnid.load(fabric=tfabric,name=name,vnid=vnid).save()
    assert cache.get_vnid_name(vnid) == name

    # perform second check, should find entry again (from cache)
    assert cache.get_vnid_name(vnid) == name

    # ensure entry is cached
    keystr = cache.get_key_str(vnid=vnid)
    assert cache.vnid_cache.get_size() == 1
    assert keystr in cache.vnid_cache.key_hash
    assert isinstance(cache.vnid_cache.search(keystr), eptVnid)

    # lookup for non-existing vnid should fail
    assert cache.get_vnid_name(12345) == ""

    # perform a flush and ensure value is no longer found within cache
    cache.handle_flush(eptVnid._classname, name=name)
    assert isinstance(cache.vnid_cache.search(keystr), hitCacheNotFound)

    # add the entry back, perform a flush, and ensure entry is not found
    assert cache.get_vnid_name(vnid) == name
    assert isinstance(cache.vnid_cache.search(keystr), eptVnid)
    cache.handle_flush(eptVnid._classname)
    assert isinstance(cache.vnid_cache.search(keystr), hitCacheNotFound)
    assert cache.vnid_cache.get_size() == 0
    assert cache.vnid_cache.head is None
    assert cache.vnid_cache.tail is None


def test_ip_is_offsubnet_full(app, func_prep):
    # ip_is_offsubnet relies on three different caches:
    #   subnet_cache
    #   epg_cache
    #   offsubnet_cache
    # A flush for a bd in epg_cache or subnet_cache should delete all cached objects within 
    # offsubhet_cache.  Ensure that is happening correctly.
    # Most importantly, ensure that offsubnet check is executing correctly.  I.e., an IP learned on
    # subnet should return False (not offsubnet) and an IP learned off subnet should return true

    cache = get_test_cache()

    # create 5 subnets, four for one BD and one for an unused BD
    vrf = 1
    assert eptEpg.load(fabric=tfabric,name="epg1",vrf=vrf,bd=1,pctag=0x1001).save()
    assert eptEpg.load(fabric=tfabric,name="epg2",vrf=vrf,bd=1,pctag=0x1002).save()
    assert eptEpg.load(fabric=tfabric,name="epg3",vrf=vrf,bd=1,pctag=0x1003).save()
    assert eptEpg.load(fabric=tfabric,name="epg4",vrf=vrf,bd=2,pctag=0x1004).save()
    assert eptEpg.load(fabric=tfabric,name="epg5",vrf=vrf,bd=1,pctag=0x1005).save()
    assert eptSubnet.load(fabric=tfabric,name="subnet1", bd=1,ip="10.1.1.1/24").save()
    assert eptSubnet.load(fabric=tfabric,name="subnet2", bd=1,ip="20.1.1.1/24").save()
    assert eptSubnet.load(fabric=tfabric,name="subnet3", bd=1,ip="2001:1:2:3:4:5:6:7/112").save()
    assert eptSubnet.load(fabric=tfabric,name="subnet4", bd=2,ip="30.1.1.1/16").save()
    assert eptSubnet.load(fabric=tfabric,name="subnet5", bd=1,ip="40.1.1.1/8").save()

    # subnet check test first (which adds entries to cache)
    def add_hits_to_cache():
        assert not cache.ip_is_offsubnet(vrf, 0x1001, "10.1.1.5") 
        assert not cache.ip_is_offsubnet(vrf, 0x1002, "10.1.1.6") 
        assert not cache.ip_is_offsubnet(vrf, 0x1003, "10.1.1.7") 
        assert not cache.ip_is_offsubnet(vrf, 0x1005, "10.1.1.9") 
        assert not cache.ip_is_offsubnet(vrf, 0x1001, "10.1.1.5") 
        assert not cache.ip_is_offsubnet(vrf, 0x1001, "20.1.1.5") 
        assert not cache.ip_is_offsubnet(vrf, 0x1001, "2001:1:2:3:4:5:6:abcd") 
        assert cache.ip_is_offsubnet(vrf, 0x1001, "2001:1:2:3:4:5:5:abcd") 
        assert cache.ip_is_offsubnet(vrf, 0x1001, "2001::abcd") 
        assert cache.ip_is_offsubnet(vrf, 0x1001, "30.1.2.5")       # wrong bd
        assert not cache.ip_is_offsubnet(vrf, 0x1004, "30.1.2.5")   # correct bd
        assert not cache.ip_is_offsubnet(vrf, 0x1001, "40.2.1.5") 
        assert not cache.ip_is_offsubnet(vrf, 0x1005, "40.3.1.5") 
        assert not cache.ip_is_offsubnet(vrf, 0xffff, "1.1.1.1")    

    add_hits_to_cache()

    # ensure epgs and subnets are present in their respective caches
    assert isinstance(cache.epg_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1001)),eptEpg)
    assert isinstance(cache.epg_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1002)),eptEpg)
    assert isinstance(cache.epg_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1003)),eptEpg)
    assert isinstance(cache.epg_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1004)),eptEpg)
    assert isinstance(cache.epg_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1005)),eptEpg)
    subnets = cache.subnet_cache.search(cache.get_key_str(bd=1))
    assert type(subnets) is list and len(subnets) == 4
    #logger.debug("subnets for bd 1: %s", subnets)
    subnet2 = cache.subnet_cache.search(cache.get_key_str(bd=2))
    assert type(subnet2) is list and len(subnet2) == 1 and subnet2[0].ip == "30.1.1.1/16"

    # ensure ip's are present within cache
    assert not cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1001,ip="10.1.1.5")).offsubnet
    assert not cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1001,ip="20.1.1.5")).offsubnet
    assert not cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1001,ip="2001:1:2:3:4:5:6:abcd")).offsubnet
    assert cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1001,ip="2001:1:2:3:4:5:5:abcd")).offsubnet
    assert cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1001,ip="2001::abcd")).offsubnet
    assert cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1001,ip="30.1.2.5")).offsubnet
    assert not cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1004,ip="30.1.2.5")).offsubnet
    assert not cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1001,ip="40.2.1.5")).offsubnet
    assert not cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1005,ip="40.3.1.5")).offsubnet
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0xffff,ip="1.1.1.1")),
            hitCacheNotFound)
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=1,ip="30.1.2.5")),
            hitCacheNotFound)

    logger.debug("offsubnet keys: %s" % cache.offsubnet_cache.key_hash.keys())
    logger.debug("offsubnet names: %s" % cache.offsubnet_cache.name_hash.keys())

    # flush of single epg name should flush all offsubnet_cache for corresponding bd (which is name)
    cache.handle_flush(eptEpg._classname, name="epg1")
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1001,ip="10.1.1.5")),
            hitCacheNotFound)
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1002,ip="10.1.1.6")),
            hitCacheNotFound)
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1003,ip="10.1.1.7")),
            hitCacheNotFound)
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1005,ip="10.1.1.9")),
            hitCacheNotFound)
    # entry for bd 2 still present
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1004,ip="30.1.2.5")),
            offsubnetCachedObject)

    # repeat for subnet flush by first adding values back into cache...
    add_hits_to_cache()
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1001,ip="10.1.1.5")),
            offsubnetCachedObject)
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1002,ip="10.1.1.6")),
            offsubnetCachedObject)
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1003,ip="10.1.1.7")),
            offsubnetCachedObject)
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1005,ip="10.1.1.9")),
            offsubnetCachedObject)

    cache.handle_flush(eptSubnet._classname, name="subnet3")
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1001,ip="10.1.1.5")),
            hitCacheNotFound)
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1002,ip="10.1.1.6")),
            hitCacheNotFound)
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1003,ip="10.1.1.7")),
            hitCacheNotFound)
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1005,ip="10.1.1.9")),
            hitCacheNotFound)
    # entry for bd 2 still present
    assert isinstance(cache.offsubnet_cache.search(cache.get_key_str(vrf=vrf,pctag=0x1004,ip="30.1.2.5")),
            offsubnetCachedObject)


