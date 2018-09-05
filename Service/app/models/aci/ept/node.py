from ...rest import Rest
from ...rest import api_register
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/node")
class eptNode(Rest):
    """ ept nodes """

    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }

    META = {
        "node": {
            "type": int,
            "key": True,
            "min": 1,
            "max": 4096,
            "description": """ 
            node id corresponding to this node. For nodes with role 'vpc', this is an emulated id
            unique to the two nodes in the vpc domain
            """,
        },
        "name": {
            "type":str, 
            "description": "node name as seen in fabric node vector",
        },
        "oobMgmtAddr": {
            "type": str,
            "description": "node out-of-band management address",
        },
        "state": {
            "type": str,
            "description": "fabricNode state indicating whether it is in-service or inactive",
        },
        "role": {
            "type": str,
            "values": ["controller", "leaf", "spine", "vpc"],
            "description": "node role to differentiate between controllers, leafs, and spines",
        },
        "address": {
            "type": int,
            "description": "32-bit physical TEP address of node",
        },
        "systemUptime": {
            "type": str,
            "description": "uptime in format hours:minutes:seconds",
        },
        "nodes": {
            "type": list,
            "description": "nodes of type vpc includes a list of id/peerIp objects",
            "default": [],
            "subtype": dict,
            "meta": {
                "id": {
                    "type": int,
                    "description": "node-id of node in this vpc domain",
                },
                "peerIp": {
                    "type": str,
                    "description": "physical TEP address of node in this vpc domain",
                },
            },
        },
    }

