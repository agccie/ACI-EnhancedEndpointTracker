from ...rest import Rest
from ...rest import api_register
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
    }

    META = {
        "vnid": {
            "type": int,
            "key": True,
            "description": """
            26-bit vxlan network identifier (VNID). For MACs this is the BD VNID and for IPs this is 
            the vrf VNID.
            """
        },
        "name": {
            "type": str,
            "description": "BD or VRF name corresponding to provided vnid",
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
