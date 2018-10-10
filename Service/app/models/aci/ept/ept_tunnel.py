from ...rest import Rest
from ...rest import api_callback
from ...rest import api_register
from .common import get_ipv4_string
import logging
import re

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

