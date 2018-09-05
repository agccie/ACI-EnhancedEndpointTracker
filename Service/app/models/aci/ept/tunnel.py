from ...rest import Rest
from ...rest import api_register
from .common import get_ipv4_string
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="eptNode", path="ept/tunnel")
class eptTunnel(Rest):
    """ ept tunnels """

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
            "key_sn": "if",
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

