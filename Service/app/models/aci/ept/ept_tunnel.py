from ... rest import Rest
from ... rest import api_callback
from ... rest import api_register
from . ept_node import eptNode
import logging
import re

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/tunnel")
class eptTunnel(Rest):
    """ provides a mapping of tunnel interface to remote node for all nodes within the fabric """

    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "db_index_unique": True,  
        "db_index": ["fabric","name"],      # fabric+name(dn) is unique (for insert/update)
        "db_index2": ["fabric", "node", "intf"],      # second index for quick lookup
    }

    META = {
        "name": {
            "type": str,
            "key": True,
            "key_sn": "tunnel",
            "key_type": "path",
            "description": "dn of object that created this tunnel (required for event handlers)",
        },
        "node": {
            "type": int,
            "min": 1,
            "max": 0xffffffff,
            "description": """ 
            node id corresponding to this node. For nodes with role 'vpc', this is an emulated id
            unique to the two nodes in the vpc domain
            """,
        },
        "intf": {
            "type": str,
            "key_sn": "tunnel",
            "description": "tunnel interface id",
        },
        "dst": {
            "type": str,
            "description": "32-bit TEP destination ipv4 address",
            "default": "0.0.0.0",   # default is only used for swagger docs example fields
        },
        "src": {
            "type": str,
            "description": "32-bit TEP source ipv4 address",
            "default": "0.0.0.0",   # default is only used for swagger docs example fields
        },
        "remote": {
            "type": int,
            "default": 0,
            "description": "remote node id corresponding the dst address of this tunnel"
        },
        "status": {
            "type": str,
            "description": "tunnel interface operational status (up or down)",
        },
        "encap": {
            "type": str,
            "description": "tunnel encapsulation type (ivxlan, vxlan, etc from tunnelIf tType)",
        },
        "flags": {
            "type": str,
            "description": "tunnel type flags (from tunnelIf 'type' field)",
        },
        "ts": {
            "type": float,
            "description": "epoch timestamp the object was created or updated",
        },
    }

    @classmethod
    @api_callback("before_create")
    def before_create(cls, data):
        # remove prefix from dst if present (happens on some dci tunnels for some reason...)
        r1 = re.search("^(?P<dst>[0-9\.]+)(/[0-9]+)?$", data["dst"])
        if r1 is not None:
            data["dst"] = r1.group("dst")
        return data

    @staticmethod
    def mo_sync(mo, tunnel):
        # if mo or tunnel is deleted, then this is a no-op
        if not mo.exists():
            return

        # when sync event happens for tunnel, perform remote mapping
        logger.debug("mo_sync for tunnel node 0x%04x, intf: %s, dst: %s", tunnel.node, tunnel.intf,
                tunnel.dst)
        remote = eptNode.find(fabric=tunnel.fabric, addr=tunnel.dst)
        if len(remote) > 0:
            logger.debug("updating remote node to 0x%04x", remote[0].node)
            tunnel.remote = remote[0].node
            tunnel.save(refresh=False)
        elif tunnel.encap == "vxlan" or "proxy" in tunnel.flags or "dci" in tunnel.flags:
            # ok to fail mapping for vxlan/proxy/dci
            logger.debug("failed to map tunnel to remote node (expected, flags: %s)", tunnel.flags)
            pass
        else:
            logger.warn("failed to map tunnel to remote node")

