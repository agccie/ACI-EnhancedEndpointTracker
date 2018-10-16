from ...rest import Rest
from ...rest import api_register
from . ept_history import eptHistory
import logging

# module level logging
logger = logging.getLogger(__name__)

# reusable attributes for src/dst move events piggy-backing on history meta for consistency
common_attr = ["ts", "intf_id", "intf_name", "pctag", "encap", "rw_mac", "rw_bd", "epg_name",
                "vnid_name"]
move_event = {
    "type": dict,
    "meta": {
        "node": {
            "type": int,
            "description": """
                node id of local node where the endpoint was learned. node id may be pseudo node 
                representing a vpc domain.
            """,
        },
    }
}
# pull common attributes from eptHistory 
for a in common_attr:
    move_event["meta"][a] = eptHistory.META["events"]["meta"][a]

@api_register(parent="fabric", path="ept/move")
class eptMove(Rest):
    """ endpoint moves within the fabric """
    logger = logger

    META_ACCESS = {
        "namespace": "move",
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }

    META = {
        "vnid": {
            "type": int,
            "key": True,
            "key_index": 1,
            "description": """
            26-bit vxlan network identifier (VNID). For MACs this is the BD VNID and for IPs this is 
            the vrf VNID.
            """
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
        "type": {
            "type": str,
            "description": "endpoint type (mac, ipv4, ipv6)",
            "values": ["mac", "ipv4", "ipv6"],
        },
        "count": {
            "type": int,
            "description": """
            total number of move events that have occurred. Note, the events list is limited by 
            the eptSettings max_endpoint_events threshold but this count will be the total count 
            including the events that have wrapped.
            """,
        },
        "events": {
            "type": list,
            "subtype": dict,
            "meta": {
                "src": move_event,
                "dst": move_event,
            },
        },
    }


class eptMoveEvent(object):
    # status will only be created or deleted, used for easy detection of deleted endpoints.
    def __init__(self, **kwargs):
        self.ts = kwargs.get("ts", 0)
        self.node = kwargs.get("node", 0)
        self.intf_id = kwargs.get("intf_id", "")
        self.intf_name = kwargs.get("intf_name", "")
        self.pctag = kwargs.get("pctag", 0)
        self.encap = kwargs.get("encap", "")
        self.rw_mac = kwargs.get("rw_mac", "")
        self.rw_bd = kwargs.get("rw_bd", 0)
        self.epg_name = kwargs.get("epg_name", "")
        self.vnid_name = kwargs.get("vnid_name", "")

    def __repr__(self):
        return "node:0x%04x %.3f: pctag:0x%x, intf:%s, encap:%s, rw:[0x%06x, %s]" % (
                self.node, self.ts, self.pctag, self.intf_id, self.encap, 
                self.rw_bd, self.rw_mac
            )

    def to_dict(self):
        """ convert object to dict for insertion into eptEndpoint events list """
        return {
            "node": self.node,
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
        """ create eptMoveEvent from dict within eptMove event list """
        return eptMoveEvent(**d)

    @staticmethod
    def from_endpoint_event(h):
        """ create eptMoveEvent from eptEndpointEvent """
        event = eptMoveEvent()
        event.ts = h.ts
        event.node = h.node
        event.pctag = h.pctag
        event.encap = h.encap
        event.intf_id = h.intf_id
        event.intf_name = h.intf_name
        event.epg_name = h.epg_name
        event.vnid_name = h.vnid_name
        event.rw_mac = h.rw_mac
        event.rw_bd = h.rw_bd
        return event

