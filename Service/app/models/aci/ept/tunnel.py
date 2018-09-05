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
        "interface": {
            "type": str,
            "key": True,
            "key_sn": "if",
            "description": "tunnel interface id",
        },
        "dst": {
            "type": int,
            "description": "32-bit TEP destination IP address (returned as string in API calls)",
            "default": "0.0.0.0",   # default is only used for swagger docs example fields
        },
        "src": {
            "type": int,
            "description": "32-bit TEP source IP address (returned as string in API calls)",
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

    @classmethod
    @api_callback("after_read")
    def after_tunnel_read(cls, data, api):
        """ convert src/dst from integer to IPv4 string on API read """
        if not api: return data
        for o in data["objects"]:
            if cls._classname in o:
                if "src" in o[cls._classname]:
                    o[cls._classname]["src"] = get_ipv4_string(o[cls._classname]["src"])
                if "dst" in o[cls._classname]:
                    o[cls._classname]["dst"] = get_ipv4_string(o[cls._classname]["dst"])
        return data

        

