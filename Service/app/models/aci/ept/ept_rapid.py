from ...rest import Rest
from ...rest import api_register
from . ept_history import eptHistory
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/rapid")
class eptRapid(Rest):
    """ rapid endpoint events within the fabric """
    logger = logger

    META_ACCESS = {
        "namespace": "rapid",
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "db_index": ["addr", "vnid", "fabric"],
        "db_shard_enable": True,
        "db_shard_index": ["addr"],
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
            total number of events that have occurred. Note, the events list is limited by 
            the eptSettings max_endpoint_events threshold but this count will be the total count 
            including the events that have wrapped.
            """
        },
        "events": {
            "type": list,
            "subtype": dict,
            "meta": {
                "ts": eptHistory.META["events"]["meta"]["ts"],
                "vnid_name": eptHistory.META["events"]["meta"]["vnid_name"],
                "count": {
                    "type": int,
                    "description": """
                    total number of events across all nodes received for this endpoint
                    """,
                },
                "rate": {
                    "type": float,
                    "description": """ rate of events per minute at time event was created"""
                },
            },
        },
    }

