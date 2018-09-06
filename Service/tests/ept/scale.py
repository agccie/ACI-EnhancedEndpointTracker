"""
simulate max scale and benchmark db performance and events per second
    
    Object          Scale   Description
    vrfs            3K
    bds             15K     5 per VRF
    epgs            15K     1 per BD
    subnets         15K     10 ipv4 and 5 ipv6 per BD for first 1K BDs
    leafs           400
    vpc-pairs       200     type 'vpc' nodes
    vpc-intf        10K     25 per vpc-pair  (25 x 2 x vpc-pairs)
    tunnels         60K     each node with tunnel to 100 vpc-teps and 50 physical teps
    endpoints       5M      mix of mac, ipv4, and ipv6 local, xr, and orphan
                            per-node local
                                vpc (2K) 500 mac, 500 ipv4, 1k ipv6
                                orphan (500) 100 mac, 200 ipv4, 200 ipv6
                            per-node remote
                                vpc (7.5K) 1.5k mac, 3k ipv4, 3k ipv6
                                ptep (2.5K) 500 mac, 1k ipv4, 1k ipv6

"""

from pymongo import IndexModel
from pymongo.errors import (DuplicateKeyError, ServerSelectionTimeoutError)
from pymongo import (ASCENDING, DESCENDING)
import logging
import os
import re
import sys
import time

# update sys path for importing test classes for app registration
sys.path.append(os.path.realpath("%s/../../" % os.path.dirname(os.path.realpath(__file__))))

# set logger to base app logger
logger = logging.getLogger("app")

scale = {
    "vrfs"                          : 3000,
    "bds_per_vrf"                   : 5,
    "epgs_per_bd"                   : 1,
    "nodes"                         : 400,
    "vpc_domains"                   : 200,
    "per_vpc_domain_vpcs"           : 25,
    "per_node_ptep_tunnel"          : 50,
    "per_node_vpc_tunnel"           : 100,
    "max_subnets"                   : 15000,    # limit total subnets (will not be across all BDs)
    "per_bd_ipv4_subnets"           : 10,
    "per_bd_ipv6_subnets"           : 5,

    # endpoint scale
    "per_node_local_vpc_mac"        : 500,
    "per_node_local_vpc_ipv4"       : 500,
    "per_node_local_vpc_ipv6"       : 1000,
    "per_node_local_orphan_mac"     : 100,
    "per_node_local_orphan_ipv4"    : 200,
    "per_node_local_orphan_ipv6"    : 200,
    "per_node_xr_vpc_mac"           : 1500,
    "per_node_xr_vpc_ipv4"          : 3000,
    "per_node_xr_vpc_ipv6"          : 3000,
    "per_node_xr_ptep_mac"          : 500,
    "per_node_xr_ptep_ipv4"         : 1000,
    "per_node_xr_ptep_ipv6"         : 1000,
}

# allocators
node_base_id                    = 0x64
vrf_base_vnid                   = 0x200000
bd_base_vnid                    = 0xe00000
pctag_base                      = 0x4000
node_ptep_base                  = 0xa000020
node_vpc_base                   = 0xa010020
v4_subnet_base                  = 0xa000100
v4_subnet_mask                  = 0xfffff00
v4_subnet_length                = 24
v6_subnet_base                  = 0x20010000000000000000000000000000
v6_subnet_mask                  = 0xffffffffffffffffffffffffffff0000
v6_subnet_length                = 112
mac_base                        = 0x0242ac000000

# named indexes
allocators = {
    "node": node_base_id,
    "vrf": vrf_base_vnid,
    "bd": bd_base_vnid,
    "pctag": pctag_base,
    "ptep": node_ptep_base,
    "vpc_tep": node_vpc_base,
    "v4subnet": v4_subnet_base,
    "v6subnet": v6_subnet_base,
    "mac": mac_base,
}
fabric_name                     = "esc-aci-fab4"
fabric                          = None      # global test fabric mo
tenant_name                     = "uni/tn-reasonably-long-tenant-name"
vrf_name                        = "%s/ctx-reasonably-long-vrf-name-{}" % tenant_name
bd_name                         = "%s/BD-reasonably-long-bd-name-{}" % tenant_name
epg_name                        = "%s/ap-reasonably-long-app-name/epg-epg-name-{}" % tenant_name
nodes                           = {}    # ptr to eptNode objects of type leaf
vpc_domains                     = {}    # ptr to eptNode objects of type vpc
bd_to_epg                       = {}    # index by bd vnid and ptr to eptEpg
ip_allocator                    = None  # IpAllocator tracking available subnets and IPs
db_pre_init                     = False # db already initialized

class SubnetAllocator(object):
    def __init__(self, subnet_type, vrf_vnid, bd_vnid, start_ip, mask):
        self.type = subnet_type
        self.vrf_vnid = vrf_vnid
        self.bd_vnid = bd_vnid
        self.start_ip = start_ip
        self.mask = mask
        self.next_ip = start_ip

    def get_next_ip(self):
        """ return next available address, None when out of addresses """
        ret = self.next_ip
        if ret & self.mask > self.start_ip:
            return None
        self.next_ip+= 1
        return ret

class IpAllocator(object):
    def __init__(self):
        self.ipv4_subnets = {}
        self.ipv6_subnets = {}
        self.ipv4_ptr = 0
        self.ipv6_ptr = 0
        self.ipv4_subnet_indexes = None
        self.ipv6_subnet_indexes = None

    def add_subnet(self, subnet):
        if subnet.type == "ipv4": 
            self.ipv4_subnets[subnet.start_ip & subnet.mask] = subnet
        else:
            self.ipv6_subnets[subnet.start_ip & subnet.mask] = subnet

    def get_next_ipv4_ip(self):
        # return tuple of subnet and next ip object where it was allocated
        # if indexes have not yet been created, create them
        if self.ipv4_subnet_indexes is None:
            self.ipv4_subnet_indexes = [i for i in self.ipv4_subnets]

        if len(self.ipv4_subnet_indexes) == 0: raise Exception("out of ipv4 subnets")
        if self.ipv4_ptr >= len(self.ipv4_subnet_indexes): self.ipv4_ptr = 0
        subnet = self.ipv4_subnets[self.ipv4_subnet_indexes[self.ipv4_ptr]]
        ip = subnet.get_next_ip()
        if ip is None:
            # mark the subnet as unusable and try again
            self.ipv4_subnets.pop(self.ipv4_ptr)
            return self.get_next_ipv4_ip()
        else:
            self.ipv4_ptr+=1
            return (subnet, ip)

    def get_next_ipv6_ip(self):
        # return tuple of subnet and next ip object where it was allocated
        # if indexes have not yet been created, create them
        if self.ipv6_subnet_indexes is None:
            self.ipv6_subnet_indexes = [i for i in self.ipv6_subnets]

        if len(self.ipv6_subnet_indexes) == 0: raise Exception("out of ipv6 subnets")
        if self.ipv6_ptr >= len(self.ipv6_subnet_indexes): self.ipv6_ptr = 0
        subnet = self.ipv6_subnets[self.ipv6_subnet_indexes[self.ipv6_ptr]]
        ip = subnet.get_next_ip()
        if ip is None:
            # mark the subnet as unusable and try again
            self.ipv6_subnets.pop(self.ipv6_ptr)
            return self.get_next_ipv6_ip()
        else:
            self.ipv6_ptr+=1
            return (subnet, ip)

class Endpoint(object):
    def __init__(self, endpoint_type, addr, vnid, node_id, intf, pctag, rw_mac=0, rw_bd=0):
        self.type = endpoint_type
        self.addr = addr
        self.vnid = vnid
        self.node_id = node_id
        self.intf = intf
        self.rw_mac = rw_mac
        self.rw_bd = rw_bd
        self.pctag = pctag
        self.remote = 0
        if "tunnel" in self.intf:
            self.remote = int(re.sub("tunnel","", self.intf))
            if self.type == "mac": 
                self.flags = "mac"
            else:
                self.flags = "ip"
        else:
            if self.type == "mac":
                self.flags ="mac,local"
            else:
                self.flags = "local"
    def __repr__(self):
        addr = self.addr

        if self.type == "mac": addr = get_mac_string(addr)
        elif self.type == "ipv4": addr = get_ipv4_string(addr)
        elif self.type == "ipv6": addr = get_ipv6_string(addr)
        return "%s %s vnid:x%x, node:%s, intf:%s, pctag:x%x, rw_mac:%s, rw_bd:x%x" % (
            self.type, 
            addr,
            self.vnid,
            self.node_id,
            self.intf,
            self.pctag,
            get_mac_string(self.rw_mac) if self.rw_mac is not None else "",
            self.rw_bd if self.rw_bd is not None else 0
        )

    def get_eptHistory(self):
        # return eptHistory object to insert into db for this endpoint
        del_event = {
            "class": "",
            "encap": "",
            "flags": "",
            "intf": "",
            "pctag": 0,
            "remote": 0,
            "rw_bd": 0,
            "rw_mac": 0,
            "status": "deleted",
            "ts": 0
        }
        create_event = {
            "class": "",
            "encap": "",
            "flags": self.flags,
            "pctag": self.pctag,
            "remote": self.remote,
            "rw_bd": self.rw_bd,
            "rw_mac": self.rw_mac,
            "status": "created",
            "ts": 0
        }
        events = [del_event for x in xrange(0, 63)]
        events.insert(0, create_event)
        addr = self.addr
        if self.type == "mac": addr = get_mac_string(addr)
        elif self.type == "ipv4": addr = get_ipv4_string(addr)
        elif self.type == "ipv6": addr = get_ipv6_string(addr)
        return eptHistory(
            fabric = fabric.fabric,
            node = self.node_id,
            vnid = self.vnid,
            addr = addr,
            type = self.type,
            events = events
        )

class EndpointTrackerNode(object):
    # track tunnels and local endpoints
    def __init__(self, node_id, tep):
        self.node_id = node_id
        self.tep = tep
        self.tunnels = {}   # index by dst-addr-str pointing to eptTunnel object
        self.vpc_tunnels = {}   # index by dst-addr-str pointing to eptTunnel object
        self.mac = {}
        self.ipv4 = {}
        self.ipv6 = {}
        self.vpc_mac = {}
        self.vpc_ipv4 = {}
        self.vpc_ipv6 = {}
        self.xr_mac_count = 0
        self.xr_ipv4_count = 0
        self.xr_ipv6_count = 0
        self.init = False
        self.pointers = {
            "mac": 0,
            "ipv4": 0,
            "ipv6": 0,
            "vpc_mac": 0,
            "vpc_ipv4": 0,
            "vpc_ipv6": 0,
        }
        self.endpoints = {
            "mac": [],
            "ipv4": [],
            "ipv6": [],
            "vpc_mac": [],
            "vpc_ipv4": [],
            "vpc_ipv6": [],
        }

    def get_next_endpoint(self, addr_type, vpc=True):
        if not self.init:
            for x in self.mac:
                ept = self.mac[x]
                if "vpc" in ept.flags: self.endpoints["vpc_mac"].append(ept)
                else: self.endpoints["mac"].append(ept)
            for x in self.ipv4:
                ept = self.ipv4[x]
                if "vpc" in ept.flags: self.endpoints["vpc_ipv4"].append(ept)
                else: self.endpoints["ipv4"].append(ept)
            for x in self.ipv6:
                ept = self.ipv6[x]
                if "vpc" in ept.flags: self.endpoints["vpc_ipv6"].append(ept)
                else: self.endpoints["ipv6"].append(ept)
        if vpc: addr_type = "vpc_%s" % addr_type
        if self.pointers[addr_type] >= len(self.endpoints[addr_type]):
            self.pointers[addr_type] = 0
        ret = self.endpoints[addr_type][self.pointers[addr_type]]
        self.pointers[addr_type]+=1
        return ret

class EndpointTracker(object):
    def __init__(self):
        self.mac = set([])
        self.ipv4 = set([])
        self.ipv6 = set([])
        # list of nodes indexed by node_id
        self.nodes = {}
        self.total_mac = 0
        self.total_ipv4 = 0
        self.total_ipv6 = 0

    def get_total_endpoints(self):
        # get unique endpoints
        return len(self.mac) + len(self.ipv4) + len(self.ipv6)

    def exists(self, addr, addr_type):
        # return true if addr exists within tracker
        if addr_type == "mac": 
            return addr in self.mac
        elif addr_type == "ipv4": 
            return addr in self.ipv4
        elif addr_type == "ipv6":
            return addr in self.ipv6
        raise Exception("unsupported addr type '%s'" % addr_type)

    def add_node(self, tracker_node):
        self.nodes[tracker_node.node_id] = tracker_node

    def add_endpoint(self, endpoint):
        # add endpoint to tracker
        if endpoint.node_id not in self.nodes: 
            raise Exception("unknown node_id %s" % endpoint.node_id)
        if endpoint.type == "mac":
            if endpoint.addr not in self.mac: self.mac.add(endpoint.addr)
            self.nodes[endpoint.node_id].mac[endpoint.addr] = endpoint
            if endpoint.node_id < 0xffff: self.total_mac+=1
        elif endpoint.type == "ipv4":
            if endpoint.addr not in self.ipv4: self.ipv4.add(endpoint.addr)
            self.nodes[endpoint.node_id].ipv4[endpoint.addr] = endpoint
            if endpoint.node_id < 0xffff: self.total_ipv4+=1
        elif endpoint.type == "ipv6":
            if endpoint.addr not in self.ipv6: self.ipv6.add(endpoint.addr)
            self.nodes[endpoint.node_id].ipv6[endpoint.addr] = endpoint
            if endpoint.node_id < 0xffff: self.total_ipv6+=1

# initialize global IpAllocator and EndpointTracker
ip_allocator = IpAllocator()
endpoint_tracker = EndpointTracker()

from app import create_app
from app.models.rest import registered_classes
from app.models.rest import Universe
from app.models.utils import pretty_print
from app.models.utils import get_db
from app.models.utils import setup_logger
from app.models.aci.ept.common import get_ipv4_prefix
from app.models.aci.ept.common import get_ipv4_string
from app.models.aci.ept.common import get_ipv6_prefix
from app.models.aci.ept.common import get_ipv6_string
from app.models.aci.ept.common import get_mac_string
from app.models.aci.fabric import Fabric
from app.models.aci.ept.common import get_ipv4_string, get_ipv6_string
from app.models.aci.ept.epg import eptEpg
from app.models.aci.ept.history import eptHistory
from app.models.aci.ept.node import eptNode
from app.models.aci.ept.subnet import eptSubnet
from app.models.aci.ept.tunnel import eptTunnel
from app.models.aci.ept.vnid import eptVnid
from app.models.aci.ept.vpc import eptVpc
db = None

def allocate_new_value(atype):
    # allocate a new vnid, subnet, or tep address
    global allocators
    increment = 1
    offset = 0
    if atype == "v4subnet":
        increment = (~v4_subnet_mask)+1
    elif atype == "v6subnet":
        increment = (~v6_subnet_mask)+1
    allocators[atype]  = allocators[atype] + increment 
    return allocators[atype]

def init_db():
    global fabric
    if db_pre_init:
        logger.debug("db already initialized")
        return

    logger.debug("initializing db")

    # get all objects registred to rest API, drop db and create with proper keys
    for classname in registered_classes:
        c = registered_classes[classname]
        # drop existing collection
        #logger.debug("dropping collection %s", c._classname)
        db[c._classname].drop()

        # create unique indexes for collection
        indexes = []
        if not c._access["expose_id"]:
            for a in c._attributes:
                if c._attributes[a].get("key", False): 
                    indexes.append((a,DESCENDING))
        if len(indexes)>0:
            #logger.debug("creating indexes for %s: %s",c._classname,indexes)
            db[c._classname].create_index(indexes, unique=True)

    # if uni is enabled then required before any other object is created
    uni = Universe()
    assert uni.save()
    fabric = Fabric(fabric=fabric_name)
    assert fabric.save()
    logger.debug("db initialized")

def build_topology():
    # build out node topology with ptep and vpc teps and tunnels along with eptVpc cache
    
    # ensure scale numbers make sense
    if scale["vpc_domains"]*2 > scale["nodes"]:
        raise Exception("number of vpc nodes (%s x 2) exceeds number of nodes (%s)" % (
            scale["vpc_domains"], 
            scale["nodes"])
        )
    if scale["per_node_ptep_tunnel"] >= scale["nodes"]:
        raise Exception("number of per_node_ptep_tunnel(%s) must be < nodes (%s)" % (
            scale["per_node_ptep_tunnel"], 
            scale["nodes"])
        )
    if scale["per_node_vpc_tunnel"] >= scale["vpc_domains"]:
        raise Exception("number of per_node_vpc_tunnel(%s) must be < vpc nodes (%s)" % (
            scale_["per_node_vpc_tunnel"], 
            scale["vpc_domains"])
        )

    bulk_tunnels = []
    bulk_nodes = []
    for n in xrange(0, scale["nodes"]):
        nid = allocate_new_value("node")
        ptep = allocate_new_value("ptep")
        addr = get_ipv4_string(ptep)
        new_node = eptNode(
                fabric=fabric.fabric, 
                node = nid,
                name="fab-%s-leaf_%s" % (fabric.fabric, nid),
                oob_addr = addr,
                addr = addr,
                role = "leaf",
                state="in-service",
        )
        bulk_nodes.append(new_node)
        nodes[nid] = new_node
        endpoint_tracker.add_node(EndpointTrackerNode(nid,addr))

    node_ids = nodes.keys()
    node_id_ptr = 0
    for n in xrange(0, scale["vpc_domains"]):
        nid1 = node_ids[node_id_ptr]
        nid2 = node_ids[node_id_ptr+1]
        vpc_nid = (nid2 << 16) + nid1
        tep = allocate_new_value("vpc_tep")
        addr = get_ipv4_string(tep)
        new_node = eptNode(
                fabric=fabric.fabric, 
                node = vpc_nid,
                name="fab-%s-vpc_%s" % (fabric.fabric, vpc_nid),
                addr = addr,
                role = "vpc",
                state="in-service",
                nodes = [
                    {"node": nid1, "addr": nodes[nid1].addr},
                    {"node": nid2, "addr": nodes[nid2].addr},
                ],
        )
        vpc_domains[vpc_nid] = new_node
        bulk_nodes.append(new_node)
        endpoint_tracker.add_node(EndpointTrackerNode(vpc_nid,addr))
        node_id_ptr+= 2
    if not db_pre_init:
        ts = time.time()
        assert eptNode.bulk_save(bulk_nodes)
        logger.info("eptNode (%s) bulk insert time: %s", len(bulk_nodes), time.time()-ts)

    # build eptVpc to po interface cache on each node within vpc domain
    bulk_vpc_intfs = []
    for nid in vpc_domains:
        for i in xrange(0, scale["per_vpc_domain_vpcs"]):
            vpc_id = 1024+i
            bulk_vpc_intfs.append(eptVpc(
                fabric = fabric.fabric,
                node = vpc_domains[nid].nodes[0]["node"],
                intf="po1%s" % vpc_id,
                vpc = vpc_id,
            ))
            bulk_vpc_intfs.append(eptVpc(
                fabric = fabric.fabric,
                node = vpc_domains[nid].nodes[1]["node"],
                intf="po2%s" % vpc_id,
                vpc = vpc_id,
            ))
    if not db_pre_init:
        ts = time.time()
        assert eptVpc.bulk_save(bulk_vpc_intfs)
        logger.debug("eptVpc (%s) bulk insert time: %s", len(bulk_vpc_intfs), time.time()-ts)

    remote_node = {"ids": nodes.keys(), "ptr": 0, "len": len(nodes)}
    remote_vpc = {"ids": vpc_domains.keys(), "ptr": 0, "len": len(vpc_domains)}
    def next_round_robin_id(vpc=False):
        # get next node id using round-robin wrapping for nodes and vpc_domains
        remote = remote_node
        if vpc: 
            remote = remote_vpc
        if remote["ptr"] >= remote["len"]:
            remote["ptr"] = 0
        ret = remote["ids"][remote["ptr"]]
        remote["ptr"] += 1
        return ret

    # build ptep and vpc tunnels
    bulk_tunnels = []
    for nid in nodes:
        # build ptep tunnels to all other nodes with exception of 'this' node
        for i in xrange(0, scale["per_node_ptep_tunnel"]):
            rid = next_round_robin_id()
            if rid == nid: 
                rid = next_round_robin_id()
            tunnel = eptTunnel(
                fabric = fabric.fabric,
                node = nid,
                intf = "tunnel%s" % rid,
                encap = "ivxlan",
                flags = "physical",
                status = "up",
                src = nodes[nid].addr,
                dst = nodes[rid].addr
            )
            bulk_tunnels.append(tunnel)
            endpoint_tracker.nodes[nid].tunnels[nodes[rid].addr] = tunnel
        # build vpc tunnels to all other vpcs with exception of 'this' node
        for i in xrange(0, scale["per_node_vpc_tunnel"]):
            rid = next_round_robin_id(vpc=True)
            if vpc_domains[rid].nodes[0]["node"] == nid or vpc_domains[rid].nodes[1]["node"] == nid:
                rid = next_round_robin_id(vpc=True)
            tunnel = eptTunnel(
                fabric = fabric.fabric,
                node = nid,
                intf = "tunnel%s" % rid,
                encap = "ivxlan",
                flags = "physical",
                status = "up",
                src = nodes[nid].addr,
                dst = vpc_domains[rid].addr
            )
            bulk_tunnels.append(tunnel)
            endpoint_tracker.nodes[nid].vpc_tunnels[vpc_domains[rid].addr] = tunnel
    if not db_pre_init:
        ts = time.time()
        assert eptTunnel.bulk_save(bulk_tunnels)
        logger.debug("eptTunnel (%s) bulk insert time: %s", len(bulk_tunnels), time.time()-ts)

def build_logical_objects():
    # build vrfs, bds, epgs, subnets and corresponding db mos
    bulk_vnids = []
    bulk_epgs = []
    bulk_subnets = []
    for i in xrange(0, scale["vrfs"]):
        vrf_vnid = allocate_new_value("vrf")
        bulk_vnids.append(eptVnid(
            fabric = fabric.fabric,
            name = vrf_name.format(i),
            pctag = allocate_new_value("pctag"),
            vnid = vrf_vnid,
            vrf = vrf_vnid,
        ))
        for b in xrange(0, scale["bds_per_vrf"]):
            bd_vnid = allocate_new_value("bd")
            bulk_vnids.append(eptVnid(
                fabric = fabric.fabric,
                name = bd_name.format(b),
                pctag = allocate_new_value("pctag"),
                vnid = bd_vnid,
                vrf = vrf_vnid,
            ))
            if len(bulk_subnets) < scale["max_subnets"]:
                for s in xrange(0, scale["per_bd_ipv4_subnets"]):
                    addr = allocate_new_value("v4subnet")
                    mask = v4_subnet_mask
                    prefix = addr & mask
                    subnet = "%s/%s" % (get_ipv4_string(prefix+1), v4_subnet_length)
                    sub1 = eptSubnet(
                        fabric = fabric.fabric,
                        subnet = subnet,
                        bd = bd_vnid,
                    )
                    bulk_subnets.append(sub1)
                    ip_allocator.add_subnet(SubnetAllocator("ipv4", vrf_vnid, bd_vnid, prefix+1, mask))
                for s in xrange(0, scale["per_bd_ipv6_subnets"]):
                    addr = allocate_new_value("v6subnet")
                    mask = v6_subnet_mask
                    prefix = addr & mask
                    subnet = "%s/%s" % (get_ipv6_string(prefix+1), v6_subnet_length)
                    sub1 = eptSubnet(
                        fabric = fabric.fabric,
                        subnet = subnet,
                        bd = bd_vnid,
                    )
                    bulk_subnets.append(sub1)
                    ip_allocator.add_subnet(SubnetAllocator("ipv6", vrf_vnid, bd_vnid, prefix+1, mask))

            for e in xrange(0, scale["epgs_per_bd"]):
                pctag = allocate_new_value("pctag")
                bulk_epgs.append(eptEpg(
                    fabric = fabric.fabric,
                    vrf = vrf_vnid,
                    bd = bd_vnid,
                    pctag = pctag,
                    is_attr_based = False
                ))
                bd_to_epg[bd_vnid] = {"pctag": pctag, "vrf": vrf_vnid}

    if not db_pre_init:
        ts = time.time()
        assert eptVnid.bulk_save(bulk_vnids)
        logger.info("eptVnid (%s) bulk insert time: %s", len(bulk_vnids), time.time()-ts)
        ts = time.time()
        assert eptEpg.bulk_save(bulk_epgs)
        logger.info("eptEpg (%s) bulk insert time: %s", len(bulk_epgs), time.time()-ts)
        ts = time.time()
        assert eptSubnet.bulk_save(bulk_subnets)
        logger.info("eptSubnet (%s) bulk insert time: %s", len(bulk_subnets), time.time()-ts)

def build_endpoints():
    # create local endpoints based on nodes, vpc_domains, and available subnets
    logger.debug("building endpoints (nodes: %s)" % len(nodes))

    for nid in nodes:
        n = nodes[nid]
        # allocate macs to use for local orphan ports (note bd and port are allocated by IP)
        local_macs = [allocate_new_value("mac") for i in xrange(0, scale["per_node_local_orphan_mac"])]
        local_mac_ptr = 0
        # allocate a new ipv4 address up to orphan ipv4
        for i in xrange(0, scale["per_node_local_orphan_ipv4"]):
            (subnet, ipv4) = ip_allocator.get_next_ipv4_ip()
            if local_mac_ptr >= len(local_macs): local_mac_ptr = 0
            mac = local_macs[local_mac_ptr]
            local_mac_ptr+=1
            intf = "eth1/1"
            epg = bd_to_epg[subnet.bd_vnid]
            # add mac endpoint to endpoint dict 
            if not endpoint_tracker.exists(mac, "mac"):
                endpoint_tracker.add_endpoint(
                    Endpoint("mac", mac, subnet.bd_vnid, nid, intf, epg["pctag"])
                )
            if endpoint_tracker.exists(ipv4,"ipv4"):
                raise Exception("duplicate ipv4 in endpoints: %s" % ipv4)
            endpoint_tracker.add_endpoint(
                Endpoint("ipv4",ipv4, subnet.vrf_vnid, nid, intf, epg["pctag"],rw_mac=mac,rw_bd=subnet.bd_vnid)
            )

        # allocate a new ipv4 address up to orphan ipv6
        for i in xrange(0, scale["per_node_local_orphan_ipv6"]):
            (subnet, ipv6) = ip_allocator.get_next_ipv6_ip()
            if local_mac_ptr >= len(local_macs): local_mac_ptr = 0
            mac = local_macs[local_mac_ptr]
            local_mac_ptr+=1
            intf = "eth1/1"
            epg = bd_to_epg[subnet.bd_vnid]
            # add mac endpoint to endpoint dict 
            if not endpoint_tracker.exists(mac, "mac"):
                endpoint_tracker.add_endpoint(
                    Endpoint("mac", mac, subnet.bd_vnid, nid, intf, epg["pctag"])
                )
            if endpoint_tracker.exists(ipv6,"ipv6"):
                raise Exception("duplicate ipv6 in endpoints: %s" % ipv6)
            endpoint_tracker.add_endpoint(
                Endpoint("ipv6",ipv6, subnet.vrf_vnid, nid, intf, epg["pctag"],rw_mac=mac,rw_bd=subnet.bd_vnid)
            )

    for vid in vpc_domains:
        n = vpc_domains[vid]
        # allocate macs to use for local vpc ports (note bd is allocated by IP)
        local_macs = [allocate_new_value("mac") for i in xrange(0, scale["per_node_local_vpc_mac"])]
        local_mac_ptr = 0
        local_vpcs = [1024+i for i in xrange(0, scale["per_vpc_domain_vpcs"])]
        local_vpc_ptr = 0
        # allocate a new ipv4 address up to orphan ipv4
        for i in xrange(0, scale["per_node_local_vpc_ipv4"]):
            (subnet, ipv4) = ip_allocator.get_next_ipv4_ip()
            if local_mac_ptr >= len(local_macs): local_mac_ptr = 0
            if local_vpc_ptr >= len(local_vpcs): local_vpc_ptr = 0
            mac = local_macs[local_mac_ptr]
            local_mac_ptr+=1
            intf = "vpc-%s" % local_vpcs[local_vpc_ptr]
            local_vpc_ptr+=1 
            epg = bd_to_epg[subnet.bd_vnid]
            # need to create the local endpoint on both nodes in the vpc domain
            nid1 = n.nodes[0]["node"]
            nid2 = n.nodes[1]["node"]
            # add mac endpoint to endpoint dict 
            if not endpoint_tracker.exists(mac, "mac"):
                ept1 = Endpoint("mac", mac, subnet.bd_vnid, nid1, intf, epg["pctag"])
                ept2 = Endpoint("mac", mac, subnet.bd_vnid, nid2, intf, epg["pctag"])
                ept3 = Endpoint("mac", mac, subnet.bd_vnid, vid, intf, epg["pctag"])
                ept1.flags+= ",vpc-attached"
                ept2.flags+= ",vpc-attached"
                ept3.flags+= ",vpc-attached"
                endpoint_tracker.add_endpoint(ept1)
                endpoint_tracker.add_endpoint(ept2)
                endpoint_tracker.add_endpoint(ept3)

            if endpoint_tracker.exists(ipv4,"ipv4"):
                raise Exception("duplicate ipv4 in endpoints: %s" % ipv4)
            ept1 = Endpoint("ipv4",ipv4, subnet.vrf_vnid, nid1, intf, epg["pctag"],rw_mac=mac,rw_bd=subnet.bd_vnid)
            ept2 = Endpoint("ipv4",ipv4, subnet.vrf_vnid, nid2, intf, epg["pctag"],rw_mac=mac,rw_bd=subnet.bd_vnid)
            ept3 = Endpoint("ipv4",ipv4, subnet.vrf_vnid, vid, intf, epg["pctag"],rw_mac=mac,rw_bd=subnet.bd_vnid)
            ept1.flags+= ",vpc-attached"
            ept2.flags+= ",vpc-attached"
            ept3.flags+= ",vpc-attached"
            endpoint_tracker.add_endpoint(ept1)
            endpoint_tracker.add_endpoint(ept2)
            endpoint_tracker.add_endpoint(ept3)

        # allocate a new ipv4 address up to orphan ipv4
        for i in xrange(0, scale["per_node_local_vpc_ipv6"]):
            (subnet, ipv6) = ip_allocator.get_next_ipv6_ip()
            if local_mac_ptr >= len(local_macs): local_mac_ptr = 0
            if local_vpc_ptr >= len(local_vpcs): local_vpc_ptr = 0
            mac = local_macs[local_mac_ptr]
            local_mac_ptr+=1
            intf = "vpc-%s" % local_vpcs[local_vpc_ptr]
            local_vpc_ptr+=1 
            epg = bd_to_epg[subnet.bd_vnid]
            # need to create the local endpoint on both nodes in the vpc domain
            nid1 = n.nodes[0]["node"]
            nid2 = n.nodes[1]["node"]
            # add mac endpoint to endpoint dict 
            if not endpoint_tracker.exists(mac, "mac"):
                ept1 = Endpoint("mac", mac, subnet.bd_vnid, nid1, intf, epg["pctag"])
                ept2 = Endpoint("mac", mac, subnet.bd_vnid, nid2, intf, epg["pctag"])
                ept3 = Endpoint("mac", mac, subnet.bd_vnid, vid, intf, epg["pctag"])
                ept1.flags+= ",vpc-attached"
                ept2.flags+= ",vpc-attached"
                ept3.flags+= ",vpc-attached"
                endpoint_tracker.add_endpoint(ept1)
                endpoint_tracker.add_endpoint(ept2)
                endpoint_tracker.add_endpoint(ept3)

            if endpoint_tracker.exists(ipv6,"ipv6"):
                raise Exception("duplicate ipv6 in endpoints: %s" % ipv6)
            ept1 = Endpoint("ipv6",ipv6, subnet.vrf_vnid, nid1, intf, epg["pctag"],rw_mac=mac,rw_bd=subnet.bd_vnid)
            ept2 = Endpoint("ipv6",ipv6, subnet.vrf_vnid, nid2, intf, epg["pctag"],rw_mac=mac,rw_bd=subnet.bd_vnid)
            ept3 = Endpoint("ipv6",ipv6, subnet.vrf_vnid, vid, intf, epg["pctag"],rw_mac=mac,rw_bd=subnet.bd_vnid)
            ept1.flags+= ",vpc-attached"
            ept2.flags+= ",vpc-attached"
            ept3.flags+= ",vpc-attached"
            endpoint_tracker.add_endpoint(ept1)
            endpoint_tracker.add_endpoint(ept2)
            endpoint_tracker.add_endpoint(ept3)

    # add local endpoint to db for all nodes
    for nid in nodes:
        bulk_history = []
        for i in endpoint_tracker.nodes[nid].mac:
            bulk_history.append(endpoint_tracker.nodes[nid].mac[i].get_eptHistory())
        for i in endpoint_tracker.nodes[nid].ipv4:
            bulk_history.append(endpoint_tracker.nodes[nid].ipv4[i].get_eptHistory())
        for i in endpoint_tracker.nodes[nid].ipv6:
            bulk_history.append(endpoint_tracker.nodes[nid].ipv6[i].get_eptHistory())
        if not db_pre_init:
            ts = time.time()
            assert eptHistory.bulk_save(bulk_history)
            logger.debug("eptHistory (%s) bulk save local endpoints node %s: %s", len(bulk_history),
                nid, time.time()-ts)

    # next step is to build xr entires on each node
    for nid in nodes:
        tracker_node = endpoint_tracker.nodes[nid]
        bulk_history = []
        for addr_type in ["mac", "ipv4", "ipv6"]:
            created_count = 0
            per_tunnel_count = int(scale["per_node_xr_ptep_%s" % addr_type]/len(tracker_node.tunnels)) + 1
            for dst in tracker_node.tunnels:
                tunnel = tracker_node.tunnels[dst]
                rid = int(re.sub("tunnel", "", tunnel.intf))
                remote_tracker_node = endpoint_tracker.nodes[rid]
                for i in xrange(0, per_tunnel_count):
                    xr = remote_tracker_node.get_next_endpoint(addr_type, vpc=False)
                    ept = Endpoint(addr_type,xr.addr, xr.vnid, nid, tunnel.intf, xr.pctag)
                    bulk_history.append(ept.get_eptHistory())
                    if addr_type == "mac":
                        tracker_node.xr_mac_count+=1
                    elif addr_type == "ipv4":
                        tracker_node.xr_ipv4_count+=1
                    elif addr_type == "ipv6":
                        tracker_node.xr_ipv6_count+=1 
                    created_count+=1
                    if created_count >= scale["per_node_xr_ptep_%s" % addr_type]: break
                if created_count >= scale["per_node_xr_ptep_%s" % addr_type]: break

        # repeat for vpc_tunnels
        for addr_type in ["mac", "ipv4", "ipv6"]:
            per_tunnel_count = int(scale["per_node_xr_vpc_%s" % addr_type]/len(tracker_node.vpc_tunnels)) + 1
            created_count = 0
            for dst in tracker_node.vpc_tunnels:
                tunnel = tracker_node.vpc_tunnels[dst]
                rid = int(re.sub("tunnel", "", tunnel.intf))
                remote_tracker_node = endpoint_tracker.nodes[rid]
                for i in xrange(0, per_tunnel_count):
                    xr = remote_tracker_node.get_next_endpoint(addr_type, vpc=True)
                    ept = Endpoint(addr_type,xr.addr, xr.vnid, nid, tunnel.intf, xr.pctag)
                    bulk_history.append(ept.get_eptHistory())
                    if addr_type == "mac":
                        tracker_node.xr_mac_count+=1
                    elif addr_type == "ipv4":
                        tracker_node.xr_ipv4_count+=1
                    elif addr_type == "ipv6":
                        tracker_node.xr_ipv6_count+=1 
                    created_count+=1
                    if created_count >= scale["per_node_xr_vpc_%s" % addr_type]: break
                if created_count >= scale["per_node_xr_vpc_%s" % addr_type]: break

        if not db_pre_init:
            ts = time.time()
            assert eptHistory.bulk_save(bulk_history)
            logger.debug("eptHistory (%s) bulk save xr endpoints node %s: %s", len(bulk_history),
                nid, time.time()-ts)


    logger.debug("building endpoints complete")

if __name__ == "__main__":
    
    import argparse
    desc = """
    scale tester.  More details to follow...
    """
    parser = argparse.ArgumentParser(description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    parser.add_argument("--cache", action="store_true", dest="cached",
        help="use db cache instead of creating all new objects")
    parser.add_argument("--debug", action="store", dest="debug", default="debug",
        help="debugging level", choices=["debug","info","warn","error"])
    args = parser.parse_args()

    # set logging level environment variable
    os.environ["LOG_LEVEL"] = "%s" % {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "error": logging.ERROR,
    }.get(args.debug, logging.DEBUG)

    # db updates through environment settings - required before initializing db
    os.environ["MONGO_HOST"] = "localhost"
    os.environ["MONGO_PORT"] = "27017"
    os.environ["MONGO_DBNAME"] = "scaledb"

    # check for cached option
    db_pre_init = args.cached

    # force logging to stdout
    setup_logger(logger, stdout=True)

    app = create_app("config.py")
    db = get_db()
    
    init_db()
    fabric = Fabric.load(fabric=fabric_name)
    build_topology()
    build_logical_objects()
    build_endpoints()

    print "nodes: %s" % len(endpoint_tracker.nodes)
    print "vpc domains: %s" % len(vpc_domains)
    print "total unique endpoints: %s" % endpoint_tracker.get_total_endpoints()
    print "mac: %s, ipv4: %s, ipv6: %s" % (
        endpoint_tracker.total_mac,
        endpoint_tracker.total_ipv4,
        endpoint_tracker.total_ipv6
    )
    total_xr_mac = 0
    total_xr_ipv4 = 0
    total_xr_ipv6 = 0
    for nid in endpoint_tracker.nodes:
        total_xr_mac+= endpoint_tracker.nodes[nid].xr_mac_count
        total_xr_ipv4+= endpoint_tracker.nodes[nid].xr_ipv4_count
        total_xr_ipv6+= endpoint_tracker.nodes[nid].xr_ipv6_count
    print "total xr_mac: %s, xr_ipv4: %s, xr_ipv6: %s" % (
            total_xr_mac,
            total_xr_ipv4,
            total_xr_ipv6
    )

    print "all done!"
    sys.exit(0)


