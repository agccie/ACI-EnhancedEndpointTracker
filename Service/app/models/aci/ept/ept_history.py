from ...rest import Rest
from ...rest import api_register
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/history")
class eptHistory(Rest):
    """ per-node endpoint history """
    logger = logger

    META_ACCESS = {
        "namespace": "history",
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "db_index": ["addr", "vnid", "fabric", "node"],
        "db_shard_enable": True,
        "db_shard_index": ["addr"],
    }

    META = {
        "node": {
            "type": int,
            "key": True,
            "key_index": 0,
            "min": 1,
            "max": 0xffffffff,
            "description": """ 
            node id corresponding to this node. For nodes with role 'vpc', this is an emulated id
            unique to the two nodes in the vpc domain
            """,
        },
        "vnid": {
            "type": int,
            "key": True,
            "key_index": 1,
            "description": """
            26-bit vxlan network identifier (VNID). For MACs this is the BD VNID and for IPs this is 
            the vrf VNID.
            """
        },
        "addr": {
            "type": str,
            "key": True,
            "key_index": 2,
            "default": "0.0.0.0",   # default is only used for swagger docs example fields
            "description": """
            for endpoints of type ipv4 this is 32-bit ipv4 address, for endpoints of type ipv6 this
            is 64-bit ipv6 address, and for endpoints of type mac this is 48-bit mac address
            """,
        },
        "type": {
            "type": str,
            "description": "endpoint type (mac or ip)",
            "values": ["mac", "ip"],
        },
        "is_stale": {
            "type": bool,
            "default": False,
            "description": """
            True if the endpoint is currently stale in the fabric. Note endpoint analysis may result
            in a temporarily stale result while processing a queue of events. Users should rely on
            eptEndpoint table is_stale state when querying stale endpoints.
            """,
        },
        "is_offsubnet": {
            "type": bool,
            "default": False,
            "description": "True if the endpoint is currently learned offsubnet",
        },
        "watch_stale_ts": {
            "type": float,
            "description": "timestamp last stale watch was set on endpoint",
        },
        "watch_offsubnet_ts": {
            "type": float,
            "description": "timestamp last offsubnet watch was set on endpoint",
        },
        "count": {
            "type": int,
            "description": """
            total number of events that have occurred. Note, the events list is limited by 
            the eptSettings max_endpoint_events threshold but this count will be the total count 
            including the events that have wrapped.
            """,
        },
        "events": {
            "type": list,
            "subtype": dict,
            "meta": {
                "classname": {
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
                    "type": list,
                    "subtype": str,
                    "description": "epm flags for endpoint event",
                },
                "tunnel_flags": {
                    "type": str,
                    "description": """ interface flags if intf_id is a tunnel """,
                },
                "encap": {
                    "type": str,
                    "description": "vlan or vxlan encap for local learn",
                },
                "intf_id": {
                    "type": str,
                    "description": "interface id where endpoint was learned",
                },
                "intf_name": {
                    "type": str,
                    "description": """ 
                    interface name. This is only relevant for port-channels, all interface types
                    should have identical intf_id and intf_name 
                    """,
                },
                "rw_mac": {
                    "type": str,
                    "description": """
                    rewrite mac address for local ipv4/ipv6 endpoints.
                    """,
                },
                "rw_bd": {
                    "type": int,
                    "description": """
                    BD VNID for mac of local ipv4/ipv6 endpoints.  This is 0 if not known.
                    """,
                },
                "epg_name": {
                    "type": str,
                    "description": "epg name based on vrf and pctag at the time of this event",
                },
                "vnid_name": {
                    "type": str,
                    "description": "vnid name based on at the time of this event",
                },
            },
        },
    }


class eptHistoryEvent(object):

    def __init__(self, **kwargs):
        self.classname = kwargs.get("classname", "")
        self.ts = kwargs.get("ts", 0)
        self.status = kwargs.get("status", "")
        self.remote = kwargs.get("remote", 0)
        self.pctag = kwargs.get("pctag", 0)
        self.flags = sorted(kwargs.get("flags", []))
        self.tunnel_flags = kwargs.get("tunnel_flags", "")
        self.encap = kwargs.get("encap", "")
        self.intf_id = kwargs.get("intf_id", "")
        self.intf_name = kwargs.get("intf_name", "")
        self.epg_name = kwargs.get("epg_name", "")
        self.vnid_name = kwargs.get("vnid_name", "")
        self.rw_mac = kwargs.get("rw_mac", "")
        self.rw_bd = kwargs.get("rw_bd", 0)

    def __repr__(self):
        return "%s %.3f: pctag:0x%x, intf:%s, encap:%s, rw:[0x%06x, %s], flags(%s):[%s], tflags:%s"%(
                self.status, self.ts, self.pctag, self.intf_id, self.encap, self.rw_bd, self.rw_mac,
                len(self.flags), ",".join(self.flags),
                self.tunnel_flags
            )

    def to_dict(self):
        """ convert object to dict for insertion into eptHistory events list """
        return {
            "classname": self.classname,
            "ts": self.ts,
            "status": self.status,
            "remote": self.remote,
            "pctag": self.pctag,
            "flags": self.flags,
            "tunnel_flags": self.tunnel_flags,
            "encap": self.encap,
            "intf_id": self.intf_id,
            "intf_name": self.intf_name,
            "epg_name": self.epg_name,
            "vnid_name": self.vnid_name,
            "rw_mac": self.rw_mac,
            "rw_bd": self.rw_bd
        }

    @staticmethod
    def from_dict(d):
        """ create eptHistoryEvent from dict within eptHistory event list """
        return eptHistoryEvent(**d)

    @staticmethod
    def from_msg(msg):
        """ create eptHistoryEvent from eptMsgWorkEpmEvent """
        event = eptHistoryEvent()
        event.classname = msg.classname
        event.ts = msg.ts
        event.status = msg.status

        if msg.status != "deleted":
            event.remote = msg.remote
            event.pctag = msg.pcTag
            event.flags = sorted(msg.flags)
            event.tunnel_flags = msg.tunnel_flags
            event.encap = msg.encap
            event.intf_id = msg.ifId
            event.intf_name = msg.ifId_name
            event.epg_name = msg.epg_name
            event.vnid_name = msg.vnid_name
        return event






