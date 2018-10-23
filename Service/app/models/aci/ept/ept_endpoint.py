
from ... rest import Rest
from ... rest import api_register
from ... rest import api_callback
from . common import get_mac_value
from . ept_history import eptHistory
from . ept_subnet import eptSubnet

import logging

# module level logging
logger = logging.getLogger(__name__)

# reusable attributes for local event piggy-backing on history meta for consistency
common_attr = ["ts", "status", "intf_id", "intf_name", "pctag", "encap", "rw_mac", "rw_bd", 
                "epg_name", "vnid_name"]
local_event = {
    "node": {
        "type": int,
        "description": """
        node id of local node where the endpoint was learned. node id may be pseudo node representing
        a vpc domain.
        """,
    },
}
# pull common attributes from eptHistory 
for a in common_attr:
    local_event[a] = eptHistory.META["events"]["meta"][a]

@api_register(parent="fabric", path="ept/endpoint")
class eptEndpoint(Rest):
    """ endpoint info 
        this is very similar to eptMove except it creates an event for unique local learns (and 
        tracks the first local learn) as well as deletes.  It's similar to APIC endpoint tracker 
        which can be used to see general learns (attach) and deletes (detach) events.  Also, all
        known endpoints are present so can be used to get total number of endpoints along with 
        searching for endpoints within the fabric.
    """
    logger = logger

    META_ACCESS = {
        "namespace": "endpoint",
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "db_index": ["addr", "vnid", "fabric"],
        "db_shard_enable": True,
        "db_shard_index": ["addr"],
        "db_index2": ["addr_byte"],      # second index for quick lookup on addr_byte
    }

    META = {
        "vnid": {
            "type": int,
            "key": True,
            "key_index": 1,
            "description": """
            26-bit vxlan network identifier (VNID). For MACs this is the BD VNID and for IPs this is 
            the vrf VNID.
            """,
        },
        "addr": {
            "type": str,
            "key": True,
            "key_index": 2,
            "default": "0.0.0.0",   # default is only used for swagger docs example fields
            "description": """
            for endpoints of type ipv4 this is 32-bit ipv4 address, for endpoints of type ipv6 this
            is 64-bit ipv6 address, and for endpoints of type mac this is 48-bit mac address
            """,
        },
        "addr_byte": {
            "type": list,
            "subtype": int,
            "description": """
            list of 32-bit integer values to create address.  For ipv4 this is single ipv4 interger
            value. For ipv6 this is 4 integers (128 bits) with most significant bits first in list.
            For mac, this is 2 integers where first integer is 16 most significant bits and second
            integer is 32 least significant bits.
            """,
        },
        "type": {
            "type": str,
            "description": "endpoint type (mac, ipv4, ipv6)",
            "default": "mac",
            "values": ["mac", "ipv4", "ipv6"],
        },
        "is_stale": {
            "type": bool,
            "default": False,
            "description": """ True if the endpoint is currently stale in the fabric """,
        },
        "is_offsubnet": {
            "type": bool,
            "default": False,
            "description": "True if the endpoint is currently learned offsubnet",
        },
        "first_learn": {
            "type": dict,
            "description": """
            first local learn event seen within the fabric. Note, this is only applicable to the 
            time the fabric monitor was running.  I.e, this the first learn the fabric monitor 
            found and may not be the first time the endpoint was seen within the fabric if the 
            monitor was not running.  This is maintained even after the 'events' list wraps
            """,
            "meta": local_event,
        },
        "count": {
            "type": int,
            "description": """
            total number of events that have occurred. Note, the events list is limited by 
            the eptSettings max_endpoint_events threshold but this count will be the total count 
            including the events that have wrapped.
            """,
        },
        "events": {
            "type": list,
            "subtype": dict,
            "description": "",
            "meta": local_event,
        },
    }

    @classmethod
    @api_callback("before_create")
    def before_create(cls, data):
        """ before create auto-detect type and update integer value for addr and mask list 
            note, here addr can be mac, ipv4, or ipv6 address
        """
        # endpoint mac always in format XX:XX:XX:XX:XX:XX
        if data["type"] == "mac":
            addr = get_mac_value(data["addr"])
            data["addr_byte"] = [
                (addr & 0xffff00000000) >> 32,
                (addr & 0x0000ffffffff),
            ]
        elif data["type"] == "ipv6":
            (data["addr_byte"], _) = eptSubnet.get_prefix_array("ipv6",data["addr"])
        else:
            (data["addr_byte"], _) = eptSubnet.get_prefix_array("ipv4",data["addr"])
        return data


class eptEndpointEvent(object):
    # status will only be created or deleted, used for easy detection of deleted endpoints.
    def __init__(self, **kwargs):
        self.ts = kwargs.get("ts", 0)
        self.node = kwargs.get("node", 0)
        self.status = kwargs.get("status", "created")
        self.intf_id = kwargs.get("intf_id", "")
        self.intf_name = kwargs.get("intf_name", "")
        self.pctag = kwargs.get("pctag", 0)
        self.encap = kwargs.get("encap", "")
        self.rw_mac = kwargs.get("rw_mac", "")
        self.rw_bd = kwargs.get("rw_bd", 0)
        self.epg_name = kwargs.get("epg_name", "")
        self.vnid_name = kwargs.get("vnid_name", "")

    def __repr__(self):
        return "%s node:0x%04x %.3f: pctag:0x%x, intf:%s, encap:%s, rw:[0x%06x, %s]" % (
                self.status, self.node, self.ts, self.pctag, self.intf_id, self.encap, 
                self.rw_bd, self.rw_mac
            )

    def to_dict(self):
        """ convert object to dict for insertion into eptEndpoint events list """
        return {
            "node": self.node,
            "status": self.status,
            "ts": self.ts,
            "pctag": self.pctag,
            "encap": self.encap,
            "intf_id": self.intf_id,
            "intf_name": self.intf_name,
            "rw_mac": self.rw_mac,
            "rw_bd": self.rw_bd,
            "epg_name": self.epg_name,
            "vnid_name": self.vnid_name,
        }

    @staticmethod
    def from_dict(d):
        """ create eptEndpointEvent from dict """
        return eptEndpointEvent(**d)

    @staticmethod
    def from_history_event(node, h):
        """ create eptEndpointEvent from eptHistoryEvent """
        event = eptEndpointEvent()
        event.node = node
        # intentionally ignore status from history event, will set directly to created/deleted 
        # before updating eptEndpoint entry
        #event.status = h.status       
        event.ts = h.ts
        event.pctag = h.pctag
        event.encap = h.encap
        event.intf_id = h.intf_id
        event.intf_name = h.intf_name
        event.epg_name = h.epg_name
        event.vnid_name = h.vnid_name
        event.rw_mac = h.rw_mac
        event.rw_bd = h.rw_bd
        return event


