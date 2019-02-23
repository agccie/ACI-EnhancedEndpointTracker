from ...rest import Rest
from ...rest import api_register
from . ept_epg import pctag_validator
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/vnid")
class eptVnid(Rest):
    """ provides a mapping of vnid to bd or vrf name with a fabric """ 
    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "db_index_unique": True,  
        "db_index": ["fabric","name"],      # fabric+name(dn) is unique (for insert/update)
        "db_index2": ["fabric", "vnid"],    # second index for quick lookup
    }

    META = {
        "name": {
            "type": str,
            "key": True,
            "key_sn": "vnid",
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
        "external": {
            "type": bool,
            "default": False,
            "description": "true if vnid is from external BD",
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
