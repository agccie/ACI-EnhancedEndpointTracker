from ...rest import Rest
from ...rest import api_register
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="eptNode", path="ept/vpc")
class eptVpc(Rest):
    """ provide mapping of port-channel interface to vpc id """ 
    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }

    META = {
        "intf": {
            "type": str,
            "key": True,
            "description": "port-channel interface id",
        },
        "vpc": {
            "type": int,
            "description": "vpc id matching between leafs in vpc domain",
        },
        "ts": {
            "type": float,
            "description": "epoch timestamp the object was created or updated",
        },
    }

