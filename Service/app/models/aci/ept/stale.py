from ...rest import Rest
from ...rest import api_register
from .history import eptHistory
import logging

# module level logging
logger = logging.getLogger(__name__)

common_attr = ["ts", "status", "remote", "pctag", "flags", "encap", "intf", "rw_mac", "rw_bd"]
stale_event = {
    "expected_remote": {
        "type": int,
        "description": """
        node id of remote node the endpoint is expected to be learned.  If the endpoint was deleted
        from the fabric (no local learn exists), then the value is set to 0
        """,
    },
    "epg_name": {
        "type": str,
        "description": "epg name at the time the event was detected",
    },
    "vnid_name": {
        "type": str,
        "description": "vrf name at the time the event was detected",
    },
}
# pull common attributes from eptHistory 
for a in common_attr:
    stale_event[a] = eptHistory.META["events"]["meta"][a]


@api_register(parent="eptNode", path="ept/stale")
class eptStale(Rest):
    """ endpoint stale events within the fabric """
    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }

    META = {
        "addr": {
            "type": str,
            "default": "0.0.0.0",   # default is only used for swagger docs example fields
            "description": """
            for endpoints of type ipv4 this is 32-bit ipv4 address, for endpoints of type ipv6 this
            is 64-bit ipv6 address, and for endpoints of type mac this is 48-bit mac address
            """,
        },
        "vnid": {
            "type": int,
            "description": """
            26-bit vxlan network identifier (VNID). For MACs this is the BD VNID and for IPs this is 
            the vrf VNID.
            """
        },
        "type": {
            "type": str,
            "description": "endpoint type (mac, ipv4, ipv6)",
            "values": ["mac", "ipv4", "ipv6"],
        },
        "count": {
            "type": int,
            "description": """
            total number of stale events that have occurred. Note, the events list is limited by the
            eptSettings max_ep_events threshold but the count will total count including the events
            that have wrapped.
            """
        },
        "events": {
            "type": list,
            "subtype": dict,
            "meta": stale_event,
        },
    }

