
from . common import get_ip_prefix
from . ept_epg import eptEpg
from . ept_node import eptNode
from . ept_pc import eptPc
from . ept_tunnel import eptTunnel
from . ept_subnet import eptSubnet
from . ept_vnid import eptVnid
from . ept_vpc import eptVpc

import logging

# module level logging
logger = logging.getLogger(__name__)

class eptCache(object):
    """ cache for ept_worker to cache common lookups

            get_peer_node       return eptNode.peer for provided node id
        
            get_tunnel_remote   return eptTunnel.remote for provided node and tunnel intf

            get_pc_vpc_id       return eptVpc.vpc for provided node and port-channel intf

            get_pc_name         return eptPc.intf_name for provided node and port-channel intf

            get_vnid_name       return eptVnid.name for provided vnid

            get_epg_name        return eptEpg.name for provided vrf and pctag

            get_subnets         return [eptSubnet] for provided bd

            ip_is_offsubnet     return bool if ip is outside of subnets for bd corresponding to 
                                vrf, pctag

            offsubnet check:
            vnid,pctag-> eptEpg.bd_vnid -> list(eptSubnets)
                                                  |
                                                  + ip ------> offsubnetCachedObject
    """
    MAX_CACHE_SIZE = 512
    KEY_DELIM = "`"             # majority of keys are integers, this should be sufficient delimiter
    def __init__(self, fabric):
        self.fabric = fabric
        self.max_cache_size = eptCache.MAX_CACHE_SIZE
        self.key_delim = eptCache.KEY_DELIM
        self.tunnel_cache = hitCache(self.max_cache_size)       # eptTunnel(node, intf) = eptTunnel
        self.node_cache = hitCache(self.max_cache_size)         # eptNode(node) = eptNode
        self.vpc_cache = hitCache(self.max_cache_size)          # eptVpc(node,intf) = eptVpc
        self.pc_cache = hitCache(self.max_cache_size)           # eptPc(node, intf) = eptPc
        self.vnid_cache = hitCache(self.max_cache_size)         # eptVnid(vnid) = eptVnid
        self.epg_cache = hitCache(self.max_cache_size)          # eptEpg(vrf,pctag) = eptEpg
        self.subnet_cache = hitCache(self.max_cache_size)       # eptSubnet(bd) = list(eptSubnet)
        self.offsubnet_cache = hitCache(self.max_cache_size)    # (vrf,pctag,ip) = offsubnetObj

    def handle_flush(self, collection_name, name=None):
        """ flush one or more entries in collection name """
        logger.debug("flush request for %s: %s", collection_name, name)
        if collection_name == eptNode._classname:
            self.node_cache.flush()     # always full cache flush for node
        elif collection_name == eptTunnel._classname:
            self.tunnel_cache.flush()   # always full cache flush for tunnel
        elif collection_name == eptVpc._classname:
            if name is not None: self.vpc_cache.remove(name, name=True)
            else: self.vpc_cache.flush()
        elif collection_name == eptPc._classname:
            if name is not None: self.Pc_cache.remove(name, name=True)
            else: self.pc_cache.flush()
        elif collection_name == eptVnid._classname:
            if name is not None: self.vnid_cache.remove(name, name=True)
            else: self.vnid_cache.flush()
        elif collection_name == eptEpg._classname:
            # need to remove one or all entries in offsubnet cache based on matching epg.bd
            if name is not None: 
                epg = self.epg_cache.search(name, name=True)
                if not isinstance(epg, hitCacheNotFound) and epg is not None:
                    self.offsubnet_flush(epg.bd)
                self.epg_cache.remove(name, name=True)
            else: 
                self.epg_cache.flush()
                self.offsubnet_cache.flush()
        elif collection_name == eptSubnet._classname:
            # need to remove on or all entries in offsubnet cache based on matching subnet.bd
            if name is not None: 
                subnets = self.subnet_cache.search(name, name=True)
                if not isinstance(subnets, hitCacheNotFound) and subnets is not None \
                    and len(subnets)>0:
                    # subnet_cache key is bd so we can just look at the first one
                    self.offsubnet_flush(subnets[0].bd)
                self.subnet_cache.remove(name, name=True)
            else: 
                self.subnet_cache.flush()
                self.offsubnet_cache.flush()
        else:
            logger.warn("flush for unsupported collection name: %s", collection_name)

    def get_key_str(self, **keys):
        """ return std key string for consistency between any method calculating cache key string"""
        return self.key_delim.join(["%s" % keys[k] for k in sorted(keys)])

    def generic_cache_lookup(self, cache, eptObject, find_one=True, db_lookup=True, **keys):
        """ check cache for object matching provided keys.  If not found then perform db lookup 
            against eptObject (Rest object).  If found, return db object else return None. Note that
            cached result may be None so returning None from cache also indicates object does not
            existing within db.

            find_one    (bool)  if not found in cache, perform db lookup and use only the first
                                match. Set to false to allow list of objects (i.e., ept_subnet list
                                based on bd)

            db_lookup   (bool)  if not found in cache, perform db lookup and add result to cache. If
                                disabled, then return None if not found in cache
        """
        keystr = self.get_key_str(**keys)
        obj = cache.search(keystr)
        if not isinstance(obj, hitCacheNotFound):
            #logger.debug("(from cache) %s %s", eptObject._classname, keys)
            return obj
        if not db_lookup: 
            # if entry not in cache and db_lookup disabled, then return None 
            return None
        obj = eptObject.find(fabric=self.fabric, **keys)
        if len(obj) == 0:
            logger.debug("(cache) not found in db: %s %s", eptObject._classname, keys)
            # add None to cache for keys to prevent db lookup on next check
            cache.push(keystr, None)
            return None
        else:
            if find_one: val = obj[0]
            else: val = obj
            # add result to cache for keys to prevent db lookup on next check
            cache.push(keystr, val)
            return val
    
    def get_peer_node(self, node):
        """ get node's peer id if in vpc domain.  If not found or an error occurs, return 0 """
        ret = self.generic_cache_lookup(self.node_cache, eptNode, node=node)
        if ret is None: return 0
        return ret.peer

    def get_tunnel_remote(self, node, intf, return_object=False):
        """ get remote node for tunnel interface. If not found or an error occurs, return 0 """
        ret = self.generic_cache_lookup(self.tunnel_cache, eptTunnel, node=node, intf=intf)
        if return_object: return ret
        if ret is None: return 0
        return ret.remote

    def get_pc_vpc_id(self, node, intf):
        """ get vpc id for provided port-channel interface, if not found return 0 """
        ret = self.generic_cache_lookup(self.vpc_cache, eptVpc, node=node, intf=intf)
        if ret is None: return 0
        return ret.vpc

    def get_pc_name(self, node, intf):
        """ get pc name for provided port-channel interface, if not found return empty string """
        ret = self.generic_cache_lookup(self.pc_cache, eptPc, node=node, intf=intf)
        if ret is None: return ""
        return ret.intf_name

    def get_vnid_name(self, vnid):
        """ return vnid name(dn) for corresponding bd or vrf vnid.  If an error occurs or vnid is
            not in db, return an empty string
        """
        ret = self.generic_cache_lookup(self.vnid_cache, eptVnid, vnid=vnid)
        if ret is None: return ""
        return ret.name

    def get_epg_name(self, vrf, pctag, return_object=False):
        """ return epg name(dn) for provided vrf and pctag combination. If an error occurs or epg
            is not found, return an empty string
            set return_object to true to return entire object instead of just epg name
        """
        ret = self.generic_cache_lookup(self.epg_cache, eptEpg, vrf=vrf, pctag=pctag)
        if return_object: return ret
        if ret is None: return ""
        return ret.name

    def get_subnets(self, bd):
        """ return list of subnet objects for provided bd.  Return an empty list of subnets not
            found or an error occurs
        """
        subnets = self.generic_cache_lookup(self.subnet_cache, eptSubnet, find_one=False, bd=bd)
        if subnets is None: return []
        return subnets

    def ip_is_offsubnet(self, vrf, pctag, ip):
        """ return bool if ip is offsubnet
            if unable to determine bd then cannot execute offsubnet check and return False.  If 
            unable to parse ip address then also an error and assume not offsubnet
        """
        ret = self.generic_cache_lookup(self.offsubnet_cache,offsubnetCachedObject, db_lookup=False,
                vrf=vrf, pctag=pctag, ip=ip)
        if ret is not None:
            return ret.offsubnet

        # get bd for corresponding epg (vrf, pctag)
        epg = self.get_epg_name(vrf, pctag, return_object=True)
        if epg is None:
            logger.warn("failed to perform subnet check for %s, epg not found(%s, %s)",ip,vrf,pctag)
            return False
        # try to parse ip string address
        (addr, mask) = get_ip_prefix(ip)
        if addr is None or mask is None:
            logger.warn("failed to parse ip address: %s", ip)
            return False
        else:
            # get list of subnets and check each for a match against the addr (assume offsubnet 
            # until matched against one of the bd subnets)
            offsubnet = True
            subnets = self.get_subnets(epg.bd)
            for s in subnets:
                (saddr, smask) = get_ip_prefix(s.ip)
                if saddr is None or smask is None:
                    logger.warn("failed to parse ip address for subnet(%s): %s", s.name, s.ip)
                    continue
                if addr & smask == saddr:
                    logger.debug("ip(%s) matched subnet(%s): %s", ip, s.name, s.ip)
                    offsubnet = False
                    break
            if offsubnet:
                logger.debug("ip(%s) not matched against any of the %s subnets in bd %s", ip, 
                    len(subnets), epg.bd)

        # add result to cache for next lookup
        keystr = self.get_key_str(vrf=vrf, pctag=pctag, ip=ip)
        self.offsubnet_cache.push(keystr, offsubnetCachedObject(epg.bd, offsubnet))
        return offsubnet

    def offsubnet_flush(self, bd):
        """ offsubnet_cache contains offsubnetCachedObjects with key of vrf,pctag,ip.  Flush occurs
            based on bd so need to walk through all nodes in list and remove nodes with provided
            bd.
        """
        remove_nodes = []
        for n in self.offsubnet_cache.get_node_list():
            if n.val is not None and hasattr(n.val, "bd") and n.val.bd == bd:
                remove_nodes.append(n)
        for n in remove_nodes:
            self.offsubnet_cache._remove_node(n)

    def log_stats(self):
        """ log statistics for each cache """
        caches = [
            "tunnel_cache",
            "node_cache", 
            "vpc_cache", 
            "epg_cache", 
            "subnet_cache", 
            "offsubnet_cache"
        ]
        logger.debug("cache stats for fabric %s", self.fabric)
        for cache_name in caches:
            c = getattr(self, cache_name)
            logger.debug("[hit: 0x%08x, miss: 0x%08x, evict: 0x%08x, flush: 0x%08x] %s", 
                c.hit_count, c.miss_count, c.evict_count, c.flush_count, cache_name)

class offsubnetCachedObject(object):
    """ cache objects support a key and val where val can contain an optionally name used mainly for
        remove(flush) operations.  We want to cache the result of offsubnet check using 
        key=vrf,pctag,ip and result=bool as well as supporting a flush for any change to eptEpg or
        eptSubnet that has bd corresponding to epg belonging to vrf,pctag. To do this, we create 
        an offsubnetCachedObject that has two attributes:
            bd = bd vnid corresponding to eptEpg/eptSubnet that created the entry
            offsubnet = boolean (true if offsubnet else false)
    """
    _classname = "offsubnet_cache"
    def __init__(self, bd, offsubnet):
        self.bd = bd
        self.offsubnet = offsubnet

class hitCacheNotFound(object):
    """ when searching for an object within hitCache and the corresponding name or key is not found,
        and instance of hitCacheNotFound object is returned.  This is to distinguish between None
        (which is a valid result), and object missing within cache
    """
    pass

class hitCache(object):
    """ hit linked list
        this class provides a linked list of nodes with a unique key. A search can be executed based
        on key or dn.  If found then corresponding val for that key or dn is returned and a hit is
        executed against the node moving it to the head of the list.  A push can also be executed to
        add a new node with key/name/value to the top of the list.  Similar to a hit operation, the
        push will move the node to the head of the list. If the list size exceeds the max cache size,
        then the node at the end of the list will be dropped.  
        
        Note, maintaining hash based key with linked list structure is much faster than previous
        O(n) lookup required to remove key from list.
    """
    def __init__(self, max_size):
        self.head = None
        self.tail = None
        self.max_size = max_size
        self.key_hash = {}
        self.name_hash = {}
        self.none_hash = {}     # objects with no name set (cached 'not found' objects)
        self.hit_count = 0
        self.miss_count = 0
        self.evict_count = 0
        self.flush_count = 0

    def __repr__(self):
        s = ["len:%s [head-key:%s, tail-key:%s], list: " % (
            len(self.key_hash),
            self.head.key if self.head is not None else None,
            self.tail.key if self.tail is not None else None,
        )]
        for n in self.get_node_list():
            s.append("%s" % node)
        return "|".join(s)

    def get_node_list(self):
        """ return a list of all nodes within the cache """
        node_list = []
        node = self.head
        while node is not None:
            node_list.append(node)
            node = node.child
        return node_list

    def flush(self):
        """ remove all entries within cache """
        self.key_hash = {}
        self.name_hash = {}
        self.none_hash = {}
        self.head = None
        self.tail = None
        self.flush+= 1

    def get_size(self):
        """ get number of nodes currently in cached linked list """
        return len(self.key_hash)

    def search(self, key, name=False):
        """ search for key within cache.  If found then trigger a push(hit) for that key and return
            corresponding value. Set name to true to perform lookup against name_hash instead of 
            key_hash.  Note, a match in name_hash does NOT trigger push/hit against object

            return hitCacheNotFound object if not found
        """
        if name:
            if key in self.name_hash:
                self.hit_count+= 1
                return self.name_hash[key].val
        elif key in self.key_hash:
            self.hit_count+= 1
            node = self.key_hash[key]
            self.push(node.key, node.val) 
            return node.val
        self.miss_count+= 1
        return hitCacheNotFound()

    def push(self, key, val):
        """ push a new or existing node to the top of the list. If the node already exists, then it
            is simply moved to the top of the list.
            if val contains 'name' attribute, then a parallel entry is added to the name_hash as 
            well as the key_hash dicts
        """
        node = None
        if key not in self.key_hash:
            node = hitCacheNode(key, val)
        else:
            node = self.key_hash[key]
            self._remove_node(node)
        # unconditionally add back to key_hash and name hash
        self.key_hash[key] = node
        for name in node.name:
            self.name_hash[name] = node
        if node.val is None:
            self.none_hash[key] = node

        # update head/tail pointers
        if self.head is None:
            self.head = node
            self.tail = node
        else:
            self._set_node_child(node, self.head)
            self.head = node
            if len(self.key_hash) > self.max_size:
                self.evict_count+=1
                self._remove_node(self.tail)

    def remove(self, key, name=False, preserve_none=False):
        """ remove a key from linked list if found.  If name is set to True, then use name_hash as
            lookup for key. if preserve_none is set to false then all nodes in none_hash are also 
            removed.
        """
        if name:
            node = self.name_hash.get(key, None)
            logger.debug("remove name %s [%s]", key, node)
        else:
            node = self.key_hash.get(key, None)
        if node is not None:
            self._remove_node(node)
        if not preserve_none:
            none_keys = self.none_hash.keys()
            for k in none_keys:
                node = self.none_hash.get(k, None)
                if node is not None:
                    self._remove_node(node)

    def _set_node_child(self, node, child):
        # add a child to a specific node, updatoing tail pointer if needed
        node.child = child
        if child is not None:
            child.parent = node
            if self.tail == node:
                self.tail = child

    def _remove_node(self, node):
        # remove a node from linked list while maintaining head/tail pointers
        self.key_hash.pop(node.key, None)
        self.none_hash.pop(node.key, None)
        for name in node.name:
            self.name_hash.pop(name, None)
        if self.head == node:
            self.head = node.child
        if self.tail == node:
            self.tail = node.parent

        if node.parent is not None:
            node.parent.child = node.child
        if node.child is not None:
            node.child.parent = node.parent
        node.parent = None
        node.child = None

class hitCacheNode(object):
    """ individual hit node within hit node linked list """
    def __init__(self, key, val):
        self.key = key
        self.val = val
        self.parent = None
        self.child = None
        self.name = []      # one or more names representing this node (many-to-one relation)
        # val is a single object or list of objects. Each object may have a name attribute which 
        # needs to be added to name list
        if type(val) is list:
            for v in val:
                if hasattr(v, "name"):
                    self.name.append(v.name)
        elif hasattr(val,"name"):
            self.name = [val.name]

    def __repr__(self):
        return " %s<-(%s.%s %s)->%s " % (
            self.parent.key if self.parent is not None else None,
            self.key, self.val, self.name,
            self.child.key if self.child is not None else None
        )

