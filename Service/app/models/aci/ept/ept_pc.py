from ...rest import Rest
from ...rest import api_callback
from ...rest import api_register
import logging
import time

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/pc")
class eptPc(Rest):
    """ provides mapping of port-channel interface to port-channel name within a fabric """ 
    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "db_index_unique": True,  
        "db_index": ["fabric","name"],      # fabric+name(dn) is unique (for insert/update)
        "db_index2": ["fabric", "node", "intf"],    # second index for quick lookup
    }

    META = {
        "name": {
            "type": str,
            "key": True,
            "key_sn": "pc",
            "description":"name(dn) for pcAggrIf that created this object",
        },
        "node": {
            "type": int,
            "min": 1,
            "max": 0xffffffff,
            "description": "node id in which this vpc belongs",
        },
        "intf": {
            "type": str,
            "description": "port-channel interface id",
        },
        "intf_name": {
            "type": str,
            "description": "policy name for port-channel interface",
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
