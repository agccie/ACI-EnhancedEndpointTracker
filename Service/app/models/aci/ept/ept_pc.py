from ...rest import Rest
from ...rest import api_callback
from ...rest import api_register
import logging
import time

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="eptNode", path="ept/pc")
class eptPc(Rest):
    """ provide mapping of port-channel interface to port-channel name """ 
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
            "key_sn": "pc",
            "description": "port-channel interface id",
        },
        "intf_name": {
            "type": str,
            "description": "policy name for port-channel interface",
        },
        "name": {
            "type": str,
            "description":"name(dn) for pcAggrIf that created this object",
        },
        "ts": {
            "type": float,
            "description": "epoch timestamp the object was created or updated",
        },
    }

    @classmethod
    @api_callback("before_create")
    def before_create(cls, data):
        """ set create time on object """
        data["ts"] = time.time()
        return data
