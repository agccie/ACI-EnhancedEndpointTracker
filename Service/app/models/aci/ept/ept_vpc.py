from ...rest import Rest
from ...rest import api_callback
from ...rest import api_register
import logging
import time

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
        "name": {
            "type": str,
            "description":"name(dn) for vpcRsVpcConf that created this object",
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

    @classmethod
    @api_callback("before_create")
    def before_vpc_create(cls, data):
        """ set create time on object """
        data["ts"] = time.time()
        return data
