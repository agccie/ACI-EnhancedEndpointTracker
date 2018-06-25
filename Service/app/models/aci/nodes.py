
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
        "id": {
            "key": True,
            "type": int,
            "description": "node identifier",
        },
        "address": {
            "description": "physical TEP address for node"
        },  
        "role":{
            "description": """
            node role. This may be normal controller/leaf/spine. Additionally,
            a vpc domain has a logical Nodes object create and will have role
            of type 'vpc'.
            """
        },
        "nodes": {
            "type": list,
            "description": "list of nodes for role type vpc",
            "subtype": dict,
            "meta": {
                "id": {
                    "type": int,
                    "description": "id of node within vpc domain",
                },
                "peerIp":{
                    "type": str,
                    "description": "TEP of peer for corresponding node id",
                },
            },
        },
        # not used but captured/stored on node creation from topSystem
        "podId":{},
        "name":{},
        "state":{},
        "systemUpTime":{},
        "oobMgmtAddr":{},
        "inbMgmtAddr":{},
    }

