from ...rest import Rest
from ...rest import api_register
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/epg")
class eptEpg(Rest):
    """ provide mapping of pctag and vrf to epg name and bd vnid """ 
    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }

    META = {
        "vrf_vnid": {
            "type": int,
            "key": True,
            "key_index": 1,
            "key_sn": "vrf",
            "description": "VRF vnid for this epg",
        },
        "pctag": {
            "type": int,
            "key": True,
            "key_index": 2,
            "description": """ 
            policy control tag representing epg.  For epgs with pctag of 'any', this is 
            programmed with a value of 0
            """,
        },
        "name": {
            "type": str,
            "description": "EPG name corresponding to provided vnid and pctag",
        },
        "bd_vnid": {
            "type": int,
            "description": "BD vnid for this epg",
        },
        "is_attr_based": {
            "type": bool,
            "default": False,
            "description": """
            true for isAttrBasedEPgs (useg epgs). This flag is used to override/ignore subnet check
            for uSeg EPGs.
            """
        },
        "ts": {
            "type": float,
            "description": "epoch timestamp the object was created or updated",
        },
    }

