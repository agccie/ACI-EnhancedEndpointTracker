
import logging,
from ..rest import (Rest, api_register)

# module level logging
logger = logging.getLogger(__name__)

@api_register(path="/aci/nodes")
class Nodes(Rest):

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False
    } 

    META = {
        "fabric": {
            "key": True,
            "description": "fabric in which this object is associated",
        },
        "node": {
            "key": True,
            "type": id,
            "description": "node in which this tunnel object exists",
        },
        "id": {
            "key": True,
            "type": str,
            "description": "tunnel interface identifier (i.e., tunnel1)",
        },
        "dest": {
            "type": str,
            "description": "tunnel destination IP (TEP)",
        },
        # not used but captured/stored on node creation from topSystem
        "operSt": {},
        "src": {},
        "tType": {},
        "type": {},
    }
