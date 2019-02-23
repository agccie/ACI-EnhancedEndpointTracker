from ...rest import Rest
from ...rest import api_register
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/node")
class eptNode(Rest):
    """ tracks the current state of all nodes within the fabric. Pseudo node objects are also
        created to represent vpc pairs and will have a role of 'vpc'.
    """

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
            "max": 0xffffffff,
            "description": """ 
            node id corresponding to this node. For nodes with role 'vpc', this is an emulated id
            unique to the two nodes in the vpc domain
            """,
        },
        "pod_id": {
            "type": int,
            "description": "pod identifier",
            "min": 1,
            "max": 4096,
        },
        "name": {
            "type":str, 
            "description": "node name as seen in fabric node vector",
        },
        "oob_addr": {
            "type": str,
            "default": "0.0.0.0",
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
        "addr": {
            "type": str,
            "default": "0.0.0.0",
            "description": "32-bit physical TEP ipv4 address of node",
        },
        "peer": {
            "type": int,
            "default": 0,
            "description": "node id of vpc peer if this node is in a vpc domain",
        },
        "nodes": {
            "type": list,
            "description": "nodes of type vpc includes a list of id/peerIp objects",
            "default": [],
            "subtype": dict,
            "meta": {
                "node": {
                    "type": int,
                    "description": "node-id of node in this vpc domain",
                },
                "addr": {
                    "type": str,
                    "description": "physical TEP address of node in this vpc domain",
                },
            },
        },
    }

