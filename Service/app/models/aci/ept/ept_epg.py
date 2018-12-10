from ...rest import Rest
from ...rest import api_register
import logging

# module level logging
logger = logging.getLogger(__name__)

def pctag_validator(classname, attribute_name, attribute_meta, value):
    # convert pctag to int, set to 0 on 'any' or any unexpected string
    try: return int(value)
    except Exception as e: return 0

@api_register(parent="fabric", path="ept/epg")
class eptEpg(Rest):
    """ provide mapping of pctag and vrf to epg name and bd vnid """ 
    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "db_index_unique": True,
        "db_index": ["fabric","name"],              # fabric+name(dn) is unique (for insert/update)
        "db_index2": ["fabric", "vrf", "pctag"],    # second index for quick lookup
    }

    META = {
        "name": {
            "type": str,
            "key": True,
            "key_sn": "epg",
            "description": "EPG name corresponding to provided vnid and pctag",
        },
        "vrf": {
            "type": int,
            "description": "VRF vnid for this epg",
        },
        "pctag": {
            "type": int,
            "description": """ 
            policy control tag representing epg.  For epgs with pctag of 'any', this is 
            programmed with a value of 0
            """,
            "validator": pctag_validator,
        },
        "bd": {
            "type": int,
            "description": "BD vnid for this epg",
        },
        "is_attr_based": {
            "type": bool,
            "default": False,
            "description": """
            true for isAttrBasedEPgs (useg epgs). This flag is used to override/ignore subnet check
            for uSeg EPGs.
            """,
        },
        "ts": {
            "type": float,
            "description": "epoch timestamp the object was created or updated",
        },
    }

