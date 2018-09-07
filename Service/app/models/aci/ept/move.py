from ...rest import Rest
from ...rest import api_register
from .history import eptHistory
import logging

# module level logging
logger = logging.getLogger(__name__)

# reusable attributes for src/dst move events piggy-backing on history meta for consistency
common_attr = ["ts", "intf", "pctag", "encap", "rw_mac", "rw_bd"]
move_event = {
    "type": dict,
    "meta": {
        "node": {
            "type": int,
            "description": "node id of local node the endpoint was learned",
        },
        "epg_name": {
            "type": str,
            "description": "epg name at the time the event was detected",
        },
        "vnid_name": {
            "type": str,
            "description": "vrf or bd name at the time the event was detected",
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
            "type": int,
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
            total number of move events that have occurred. Note, the events list is limited by the
            eptSettings max_ep_events threshold but the count will total count including the events
            that have wrapped.
            """
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

