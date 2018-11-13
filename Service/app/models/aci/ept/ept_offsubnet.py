from ...rest import Rest
from ...rest import api_register
from . common import get_vpc_domain_name
from . ept_history import eptHistory
import logging

# module level logging
logger = logging.getLogger(__name__)

common_attr = ["ts", "pctag", "encap", "intf_name", "intf_id", "rw_mac", "rw_bd", "remote", 
                "epg_name", "vnid_name"]
offsubnet_event = { }
# pull common attributes from eptHistory 
for a in common_attr:
    offsubnet_event[a] = eptHistory.META["events"]["meta"][a]


@api_register(parent="fabric", path="ept/offsubnet")
class eptOffSubnet(Rest):
    """ endpoint offsubnet events within the fabric """
    logger = logger

    META_ACCESS = {
        "namespace": "offsubnet",
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "db_index": ["addr", "vnid", "node", "fabric"],
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
            "description": "endpoint type (mac, ipv4, ipv6)",
            "values": ["mac", "ipv4", "ipv6"],
        },
        "count": {
            "type": int,
            "description": """
            total number of offsubnet events that have occurred. Note, the events list is limited by 
            the eptSettings max_endpoint_events threshold but this count will be the total count 
            including the events that have wrapped.
            """
        },
        "events": {
            "type": list,
            "subtype": dict,
            "meta": offsubnet_event,
        },
    }


class eptOffSubnetEvent(object):
    def __init__(self, **kwargs):
        self.ts = kwargs.get("ts", 0)
        self.intf_id = kwargs.get("intf_id", "")
        self.intf_name = kwargs.get("intf_name", "")
        self.pctag = kwargs.get("pctag", 0)
        self.encap = kwargs.get("encap", "")
        self.rw_mac = kwargs.get("rw_mac", "")
        self.rw_bd = kwargs.get("rw_bd", 0)
        self.remote = kwargs.get("remote", 0)
        self.epg_name = kwargs.get("epg_name", "")
        self.vnid_name = kwargs.get("vnid_name", "")

    def __repr__(self):
        return "%.3f: pctag:0x%x, intf:%s, encap:%s, rw:[0x%06x, %s], remote:0x%04x" % (
                self.ts, self.pctag, self.intf_id, self.encap, self.rw_bd, self.rw_mac, self.remote
            )

    def is_duplicate(self, event):
        """ check if this offsubnet event is logically the same as the provided offsubnet object """
        # only checking remote and pctag (which drives epg/bd/subnets), if the same then suppress
        # the offsubnet event
        return (self.remote == event.remote and self.pctag == event.pctag)

    def to_dict(self):
        """ convert object to dict for insertion into eptEndpoint events list """
        return {
            "ts": self.ts,
            "pctag": self.pctag,
            "encap": self.encap,
            "intf_id": self.intf_id,
            "intf_name": self.intf_name,
            "rw_mac": self.rw_mac,
            "rw_bd": self.rw_bd,
            "remote": self.remote,
            "epg_name": self.epg_name,
            "vnid_name": self.vnid_name,
        }

    def notify_string(self, include_rw=False):
        """ return string formatted for notify message """
        return "[interface:%s, encap:%s, pctag:%s, epg:%s, mac:%s, remote:%s]" % (
            self.intf_name,
            self.encap,
            self.pctag,
            self.epg_name,
            "-" if len(self.rw_mac)==0 else self.rw_mac,
            "-" if self.remote==0 else get_vpc_domain_name(self.remote),
        )

    @staticmethod
    def from_dict(d):
        """ create eptOffSubnetEvent from dict """
        return eptOffSubnetEvent(**d)

    @staticmethod
    def from_history_event(h):
        """ create eptOffSubnetEvent from eptHistoryEvent """
        event = eptOffSubnetEvent()
        event.ts = h.ts
        event.pctag = h.pctag
        event.encap = h.encap
        event.intf_id = h.intf_id
        event.intf_name = h.intf_name
        event.epg_name = h.epg_name
        event.vnid_name = h.vnid_name
        event.rw_mac = h.rw_mac
        event.rw_bd = h.rw_bd
        event.remote = h.remote
        return event



