from ...rest import Rest
from ...rest import api_register
from . common import get_vpc_domain_name
from . ept_history import eptHistory
import logging

# module level logging
logger = logging.getLogger(__name__)

common_attr = ["ts", "remote", "pctag", "flags", "encap", "intf_id", "intf_name",
                "epg_name", "vnid_name"]
stale_event = {
    "expected_remote": {
        "type": int,
        "description": """
        node id of remote node the endpoint is expected to be learned.  If the endpoint was deleted
        from the fabric (no local learn exists), then the value is set to 0
        """,
    },
}
# pull common attributes from eptHistory 
for a in common_attr:
    stale_event[a] = eptHistory.META["events"]["meta"][a]


@api_register(parent="fabric", path="ept/stale")
class eptStale(Rest):
    """ endpoint stale events within the fabric """
    logger = logger

    META_ACCESS = {
        "namespace": "stale",
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
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
            "description": "endpoint type (mac, ipv4, ipv6)",
            "values": ["mac", "ipv4", "ipv6"],
        },
        "count": {
            "type": int,
            "description": """
            total number of stale events that have occurred. Note, the events list is limited by the
            eptSettings max_endpoint_events threshold but this count will be the total count 
            including the events that have wrapped.
            """
        },
        "events": {
            "type": list,
            "subtype": dict,
            "meta": stale_event,
        },
    }


class eptStaleEvent(object):
    def __init__(self, **kwargs):
        self.ts = kwargs.get("ts", 0)
        self.remote = kwargs.get("remote", 0)
        self.expected_remote = kwargs.get("expected_remote", 0)
        self.intf_id = kwargs.get("intf_id", "")
        self.intf_name = kwargs.get("intf_name", "")
        self.pctag = kwargs.get("pctag", 0)
        self.encap = kwargs.get("encap", "")
        self.flags = kwargs.get("flags", [])
        self.epg_name = kwargs.get("epg_name", "")
        self.vnid_name = kwargs.get("vnid_name", "")

    def __repr__(self):
        return "%.3f: pctag:0x%x, intf:%s, encap:%s, flags(%s):[%s], remote/expected:0x%04x/0x%04x"%(
                self.ts, self.pctag, self.intf_id, self.encap, 
                len(self.flags),
                ",".join(self.flags),
                self.remote, self.expected_remote
            )

    def to_dict(self):
        """ convert object to dict for insertion into eptEndpoint events list """
        return {
            "ts": self.ts,
            "remote": self.remote,
            "expected_remote": self.expected_remote,
            "pctag": self.pctag,
            "encap": self.encap,
            "intf_id": self.intf_id,
            "intf_name": self.intf_name,
            "flags": self.flags,
            "epg_name": self.epg_name,
            "vnid_name": self.vnid_name,
        }

    def notify_string(self):
        """ return string formatted for notify message """
        return "[interface:%s, encap:%s, pctag:%s, epg:%s%s, remote:%s, expected:%s]" % (
            self.intf_name,
            self.encap,
            self.pctag,
            self.epg_name,
            "-" if self.remote==0 else get_vpc_domain_name(self.remote),
            "-" if self.expected_remote==0 else get_vpc_domain_name(self.expected_remote),
        )

    @staticmethod
    def from_dict(d):
        """ create eptStaleEvent from dict """
        return eptStaleEvent(**d)

    @staticmethod
    def from_history_event(expected_remote, h):
        """ create eptStaleEvent from eptHistoryEvent """
        event = eptStaleEvent()
        event.expected_remote = expected_remote
        event.ts = h.ts
        event.remote = h.remote
        event.pctag = h.pctag
        event.encap = h.encap
        event.flags = h.flags
        event.intf_id = h.intf_id
        event.intf_name = h.intf_name
        event.epg_name = h.epg_name
        event.vnid_name = h.vnid_name
        return event


