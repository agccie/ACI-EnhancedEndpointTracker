from ...rest import Rest
from ...rest import api_register
from ...rest import api_callback

import logging
import re

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/vnsrslifctxtobd")
class eptVnsRsLIfCtxToBD(Rest):
    """ maintain mapping of vnsLifCtx to BD vnid  
        since vnsLIfCtx objects can anchor fvSubnets we need quick lookup of dn to bd vnid
    """

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }

    META = {
        "name": {
            "type": str,
            "key": True,
            "description": "vnsLIfCtx dn",
        },
        "bd_dn": {
            "type": str,
            "description": "BD DN for vnsLIfCtx",
        },
        "bd": {
            "type": int,
            "description": "BD vnid for vnsLIfCtx",
        },
        "parent": {
            "type": str,
            "description": "dn for parent vnsLIfCtx",
        },
    }

    @classmethod
    @api_callback("before_create")
    def before_create(cls, data):
        data["parent"] = re.sub("/rsLIfCtxToBD$", "", data["name"])
        return data

