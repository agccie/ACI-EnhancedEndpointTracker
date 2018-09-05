from ...rest import Rest
from ...rest import api_register
from ...rest import api_callback
from .common import api_read_format_addr
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="eptNode", path="ept/history")
class eptHistory(Rest):
    """ endpoint history """
    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }

    META = {
        "addr": {
            "type": str,
            "default": "0.0.0.0",   # default is only used for swagger docs example fields
            "description": """
            for endpoints of type ipv4 this is 32-bit ipv4 address, for endpoints of type ipv6 this
            is 64-bit ipv6 address, and for endpoints of type mac this is 48-bit mac address
            """,
        },
        "vnid": {
            "type": int,
            "description": """
            26-bit vxlan network identifier (VNID). For MACs this is the BD VNID and for IPs this is 
            the vrf VNID.
            """
        },
        "type": {
            "type": str,
            "description": "endpoint type (mac, ipv4, ipv6)",
            "values": ["mac", "ipv4", "ipv6"],
        },
        "is_stale": {
            "type": bool,
            "default": False,
            "description": """
            True if the endpoint is currently stale in the fabric. Note endpoint analysis may result
            in a temporarily stale result while processing a queue of events. Users should ensure 
            that eptHistory.is_stale is true AND that the event was creating in the eptStale table
            before concluding that the endpoint is truly stale.
            """,
        },
        "is_offsubnet": {
            "type": bool,
            "default": False,
            "description": "True if the endpoint is currently learned offsubnet",
        },
        "events": {
            "type": list,
            "subtype": dict,
            "meta": {
                "class": {
                    "type": str,
                    "description": "epm classname that triggered the event"
                },
                "ts": {
                    "type": float,
                    "description": "epoch timestamp the event was detected",
                },
                "status": {
                    "type": str,
                    "description": "current status of the endpoint (created, modified, deleted)",
                    "values": ["created", "modified", "deleted"],
                },
                "remote": {
                    "type": int,
                    "description": """
                    resolved tunnel to node id for remote learns. Note, this may be an emulated 
                    node-id representing a vpc pair.  See eptNode object for more details
                    """
                },
                "pctag": {
                    "type": int,
                    "description": """ 
                    policy control tag representing epg.  For epgs with pctag of 'any', this is 
                    programmed with a value of 0
                    """,
                },
                "flags": {
                    "type": str,
                    "description": "epm flags for endpoint event",
                },
                "encap": {
                    "type": str,
                    "description": "vlan or vxlan encap for local learn",
                },
                "intf": {
                    "type": str,
                    "description": "interface id where endpoint was learned",
                },
                "rw_mac": {
                    "type": int,
                    "description": """
                    rewrite mac address for local ipv4/ipv6 endpoints. For API calls this is
                    as string representation of MAC address or an empty string if not set (0).
                    """,
                },
                "rw_bd": {
                    "type": int,
                    "description": """
                    BD VNID for mac of local ipv4/ipv6 endpoints.  This is 0 if not known.
                    """,
                },
            },
        },
    }

    @classmethod
    @api_callback("after_read")
    def after_history_read(cls, data, api):
        """ convert event rw_mac """
        if not api: return data
        return api_read_format_addr(data)


