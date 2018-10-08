
from . ept_epg import eptEpg
from . ept_node import eptNode
from . ept_tunnel import eptTunnel
from . ept_subnet import eptSubnet
from . ept_vnid import eptVnid
from . ept_vpc import eptVpc

import logging

# module level logging
logger = logging.getLogger(__name__)

class eptCache(object):
    """ cache for ept_worker to cache common lookups

            Cache           Cache-index                     Cache-flush-index
            node            node -> eptNode.peer            [no flush support for eptNode.name]
            tunnel          node,intf -> eptTunnel.remote   [no flush support for eptTunnel.name]
            vpc             node,intf -> eptVpc.vpc         eptVpc.name -> eptVpc
            vnid_name       vnid -> eptVnid.name            eptVnid.name -> eptVnid
            epg_name        vrf_vnid,pctag -> eptEpg        eptEpg.name -> eptEpg
            subnet          bd_vnid -> list(eptSubnets)     eptSubnet.name -> bd vnid
            offsubnet       ip,vnid,pctag -> bool           [flush via eptEpg and eptSubnet]
            
            offsubnet check:
            vnid,pctag-> eptEpg.bd_vnid -> list(eptSubnets)
                                                  |
                                                  + ip ------> offsubnet?

            if receive a flush for eptEpg or eptSubnet, remove entry for bd_vnid within subnet cache
            and 
    """
    MAX_CACHE_SIZE = 512
    KEY_DELIM = "`"             # majority of keys are integers, this should be sufficient delimiter
    def __init__(self, fabric):
        self.fabric = fabric
        self.max_cache_size = eptCache.MAX_CACHE_SIZE
        self.key_delim = eptCache.KEY_DELIM
        self.tunnel_cache = hitLL(self.max_cache_size)      # eptTunnel(node, intf) = eptTunnel
        self.node_cache = hitLL(self.max_cache_size)        # eptNode(node) = eptNode
        self.vpc_cache = hitLL(self.max_cache_size)         # eptVpc(node,intf) = eptVpc
        self.vnid_cache = hitLL(self.max_cache_size)        # eptVnid(vnid) = eptVnid
        self.epg_cache = hitLL(self.max_cache_size)         # eptEpg(vrf,pctag) = eptEpg
        self.subnet_cache = hitLL(self.max_cache_size)      # eptSubnet(bd) = list(eptSubnet)

    def handle_flush(self, collection_name, name=None):
        """ flush one or more entries in collection name """
        logger.debug("flush request for %s: %s", collection_name, name)
        if collection_name == eptTunnel._classname:
            self.tunnel_cache = {}      # always full cache flush for tunnel
        elif collection_name == eptNode._classname:
            self.node_cache = {}        # always full cache flush for node
        elif collection_name == eptVpc._classname:
            if name is not None: self.vpc_cache.remove(name, name=True)
            else: self.vpc_cache = {}
        elif collection_name == eptVnid._classname:
            if name is not None: self.vnid_cache.remove(name, name=True)
            else: self.vnid_cache = {}
        elif collection_name == eptEpg._classname:
            if name is not None: self.epg_cache.remove(name, name=True)
            else: self.epg_cache = {}
        elif collection_name == eptSubnet._classname:
            if name is not None: self.subnet_cache.remove(name, name=True)
            else: self.subnet_cache = {}
        else:
            logger.warn("flush for unsupported collection name: %s", collection_name)

    def generic_cache_lookup(self, cache, eptObject, find_one=True, **keys):
        """ check cache for object matching provided keys.  If not found then perform db lookup 
            against eptObject (Rest object).  If found return db object else return None
            set find_one=False to return all objects that match keys
        """
        keystr = self.key_delim.join([k for k in keys])
        obj = cache.search(keystr)
        if obj is not None:
            logger.debug("(cache) %s %s", eptObject._classname, keys)
            return obj
        obj = eptObject.find(fabric=self.fabric, *keys)
        if len(obj) == 0:
            logger.debug("db key not found: %s %s", eptObject._classname, keys)
            # add None to cache for keys
            cache.push(keystr, None)
            return None
        else:
            if find_one: val = obj[0]
            else: val = obj
            # add to cache for next lookup
            # cache.push(keystr, 
            # TODO - figure out how to handle flush for list of objects...
            return val
            

    def get_peer_node(self, node):
        """ get node's peer id if in vpc domain.  If not found or an error occurs, return 0 """
        keystr = "%s"%node
        obj = self.node_cache.search(keystr)
        if obj is not None:
            pass

    def get_vnid_name(self, vnid):
        """ return vnid name(dn) for corresponding bd or vrf vnid.  If an error occurs or vnid is
            not in db, return an empty string
        """
        keystr = "%s"%vnid
        obj = self.vnid_cache.search(keystr)
        if obj is not None:
            logger.debug("get_vnid_name(%s) returning from cache: %s", vnid, obj.name)
            return obj.name
        obj = eptVnid.find(fabric=self.fabric, vnid=vnid)
        if len(obj) == 0:
            logger.debug("vnid %s not found", vnid)
            return ""
        self.vnid_cache.push(keystr, obj[0])
        return obj[0].vnid


class hitLL(object):
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

    def __repr__(self):
        s = ["len:%s [head-key:%s, tail-key:%s], list: " % (
            len(self.key_hash),
            self.head.key if self.head is not None else None,
            self.tail.key if self.tail is not None else None,
        )]
        node = self.head
        while node is not None:
            s.append("%s" % node)
            node = node.child
        return "|".join(s)

    def search(self, key):
        """ search for key within cache.  If found then trigger a push(hit) for that key.
            return None if not found
        """
        if key in self.key_hash:
            node = self.key_hash[key]
            self.push(node.key, node.val, node.name)
            return node.val
        return None

    def push(self, key, val):
        """ push a new or existing node to the top of the list. If the node already exists, then it
            is simply moved to the top of the list.
            if val contains 'name' attribute, then a parallel entry is added to the name_hash as 
            well as the key_hash dicts
        """
        node = None
        if key not in self.key_hash:
            node = hitNodeLL(key, val)
        else:
            node = self.key_hash[key]
            self._remove_node(node)
        # unconditionally add back to key_hash
        self.key_hash[key] = node
        if node.name is not None:
            self.name_hash[node.name] = node
        else:
            self.none_hash[key] = node

        # update head/tail pointers
        if self.head is None:
            self.head = node
            self.tail = node
        else:
            self._set_node_child(node, self.head)
            self.head = node
            if len(self.key_hash) > self.max_size:
                self._remove_node(self.tail)

    def remove(self, key, name=False, preserve_none=False):
        """ remove a key from linked list if found.  If name is set to True, then use name_hash as
            lookup for key. if preserve_none is set to false then all nodes in none_hash are also 
            removed.
        """
        if name:
            node = self.name_hash(key, None)
        else:
            node = self.key_hash(key, None)
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
        if node.name is not None:
            self.name_hash.pop(node.name, None)
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

class hitNodeLL(object):
    """ individual hit node within hit node linked list """
    def __init__(self, key, val):
        self.key = key
        self.val = val
        if hasattr(val,"name"):
            self.name = val.name
        else:
            self.name = None
        self.parent = None
        self.child = None

    def __repr__(self):
        return " %s<-(%s.%s %s)->%s " % (
            self.parent.key if self.parent is not None else None,
            self.key, self.val, self.name,
            self.child.key if self.child is not None else None
        )

