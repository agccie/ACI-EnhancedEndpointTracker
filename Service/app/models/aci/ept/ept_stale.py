from ...rest import Rest
from ...rest import api_register
from . ept_history import eptHistory
import logging

# module level logging
logger = logging.getLogger(__name__)

common_attr = ["ts", "status", "remote", "pctag", "flags", "encap", "intf_id", "intf_name",
                "epg_name", "vnid_name"]
stale_event = {
    "expected_remote": {
        "type": int,
        "description": """
        node id of remote node the endpoint is expected to be learned.  If the endpoint was deleted
        from the fabric (no local learn exists), then the value is set to 0
        """,
    },
}
# pull common attributes from eptHistory 
for a in common_attr:
    stale_event[a] = eptHistory.META["events"]["meta"][a]


@api_register(parent="fabric", path="ept/stale")
class eptStale(Rest):
    """ endpoint stale events within the fabric """
    logger = logger

    META_ACCESS = {
        "namespace": "stale",
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }

    META = {
        "node": {
            "type": int,
            "key": True,
            "key_index": 0,
            "min": 1,
            "max": 0xffffffff,
            "description": """ 
            node id corresponding to this node. For nodes with role 'vpc', this is an emulated id
            unique to the two nodes in the vpc domain
            """,
        },
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
            total number of stale events that have occurred. Note, the events list is limited by the
            eptSettings max_endpoint_events threshold but this count will be the total count 
            including the events that have wrapped.
            """
        },
        "events": {
            "type": list,
            "subtype": dict,
            "meta": stale_event,
        },
    }

