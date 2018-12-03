from ...rest import Rest
from ...rest import api_register
from . common import common_event_attribute
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/remediate")
class eptRemediate(Rest):
    """ ept remediation events. this includes API clear events or auto-clear events """
    logger = logger

    META_ACCESS = {
        "namespace": "remediate",
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "db_index": ["addr", "vnid", "fabric", "node"],
        "db_shard_enable": True,
        "db_shard_index": ["addr"],
    }

    META = {
        "node": {
            "type": int,
            "key": True,
            "key_index": 0,
            "min": 1,
            "max": 0xffffffff,
            "description": """ node id corresponding to this node. """,
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
            "default": "mac",
            "values": ["mac", "ipv4", "ipv6"],
        },
        "count": {
            "type": int,
            "description": """
            total number of events that have occurred. Note, the events list is limited by the 
            eptSettings max_per_node_endpoint_events threshold but this count will be the 
            total count including the events that have wrapped.
            """,
        },
        "events": {
            "type": list,
            "subtype": dict,
            "meta": {
                "ts": {
                    "type": float,
                    "description": "epoch timestamp the event was detected",
                },
                "ts": common_event_attribute["ts"],
                "vnid_name": common_event_attribute["vnid_name"],
                "action": {
                    "type": str,
                    "values": ["clear"],
                    "default": "clear",
                    "description": """ 
                    event action performed. 'clear' is the only current remediation action.
                    """,
                },
                "reason": {
                    "type": str,
                    "values": ["stale", "offsubnet", "api"],
                    "description": "reason or source of the remediation",
                },
            }
        },
    }

