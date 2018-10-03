from ...rest import Rest
from ...rest import api_register
from . ept_epg import pctag_validator
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/vnid")
class eptVnid(Rest):
    """ provide mapping of vnid to bd or vrf name """ 
    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "db_index_unique": False,   # db_index is intentionally different from mode keys
        "db_index": ["fabric", "vnid"],
    }

    META = {
        "name": {
            "type": str,
            "key": True,
            "key_type": "path",
            "description": "BD or VRF name corresponding to provided vnid",
        },
        "vnid": {
            "type": int,
            "description": """
            26-bit vxlan network identifier (VNID). For MACs this is the BD VNID and for IPs this is 
            the vrf VNID.
            """
        },
        "vrf": {
            "type": int,
            "description": "for bd vnids this is corresponding vrf vnid, else this is same as vnid",
        },
        "pctag": {
            "type": int,
            "description": """ 
            policy control tag representing epg.  For epgs with pctag of 'any', this is 
            programmed with a value of 0
            """,
            "validator": pctag_validator,
        },
        "encap": {
            "type": str,
            "description": "vlan or vxlan encap for external BDs",
        },
        "ts": {
            "type": float,
            "description": "epoch timestamp the object was created or updated",
        },
    }
