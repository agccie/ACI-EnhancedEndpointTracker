from ...rest import Rest
from ...rest import api_register
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/subnet")
class eptSubnet(Rest):
    """ provide mapping of BD vnid to list of configured subnets """ 
    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }

    META = {
        "bd_vnid": {
            "type": int,
            "key": True,
            "key_index": 1,
            "key_sn": "bd",
            "description": "BD vnid for this epg",
        },
        "subnet": {
            "type": str,
            "key": True,
            "key_index": 2,
            "description": "ipv4 or ipv6 subnet prefix"
        },
        "type": {
            "type": str,
            "description": "subnet prefix type of ipv4 or ipv6",
            "values": ["ipv4", "ipv6"],
        },
        "addr": {
            "type": list,
            "subtype": int,
            "description": """
            list of 32-bit integer values to create address.  For ipv4 this is single ipv4 interger
            value. For ipv6 this is 4 integers (128 bits) with most significant bits first in list
            """,
        },
        "mask": {
            "type": list,
            "subtype": int,
            "description": """
            list of 32-bit integer values to create mask.  For ipv4 this is single ipv4 interger
            value. For ipv6 this is 4 integers (128 bits) with most significant bits first in list
            """,
        },
        "ts": {
            "type": float,
            "description": "epoch timestamp the object was created or updated",
        },
    }

