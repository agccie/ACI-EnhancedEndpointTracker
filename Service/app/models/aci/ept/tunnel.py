from ...rest import Rest
from ...rest import api_register
from ...rest import api_callback
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
        "operSt": {
            "type": str,
            "description": "tunnel interface operational status (generally 'up' or 'down')",
        },
        "tType": {
            "type": str,
            "description": "tunnel encapsulation type (ivxlan, vxlan, etc...)",
        },
        "type": {
            "type": str,
            "description": "tunnel type flags",
        },
    }


