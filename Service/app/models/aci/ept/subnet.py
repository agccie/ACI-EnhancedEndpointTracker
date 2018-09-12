from ...rest import Rest
from ...rest import api_register
from ...rest import api_callback
from .common import get_ipv4_prefix
from .common import get_ipv6_prefix
import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/subnet")
class eptSubnet(Rest):
    """ provide mapping of BD vnid to list of configured subnets """ 
    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }

    META = {
        "bd": {
            "type": int,
            "key": True,
            "key_index": 1,
            "key_sn": "bd",
            "description": "BD vnid for this epg",
        },
        "subnet": {
            "type": str,
            "key": True,
            "key_index": 2,
            "key_type": "path",
            "description": "ipv4 or ipv6 subnet prefix"
        },
        "type": {
            "type": str,
            "description": "subnet prefix type of ipv4 or ipv6",
            "values": ["ipv4", "ipv6"],
        },
        "addr_byte": {
            "type": list,
            "subtype": int,
            "description": """
            list of 32-bit integer values to create address.  For ipv4 this is single ipv4 interger
            value. For ipv6 this is 4 integers (128 bits) with most significant bits first in list
            """,
        },
        "mask_byte": {
            "type": list,
            "subtype": int,
            "description": """
            list of 32-bit integer values to create mask.  For ipv4 this is single ipv4 interger
            value. For ipv6 this is 4 integers (128 bits) with most significant bits first in list
            """,
        },
        "ts": {
            "type": float,
            "description": "epoch timestamp the object was created or updated",
        },
    }

    @classmethod
    @api_callback("before_create")
    def before_subnet_create(cls, data):
        """ before create auto-detect type and update integer value for addr and mask list """
        if ":" in data["subnet"]:
            data["type"] = "ipv6"
            (data["addr_byte"],data["mask_byte"]) = eptSubnet.get_prefix_array("ipv6",data["subnet"])
        else:
            data["type"] = "ipv4"
            (data["addr_byte"],data["mask_byte"]) = eptSubnet.get_prefix_array("ipv4",data["subnet"])
        return data

    @staticmethod
    def get_prefix_array(prefix_type, prefix):
        """ for ipv4 or ipv6 prefix, return tuple (addr_byte list, mask_byte list) """
        if prefix_type == "ipv4":
            (addr, mask) = get_ipv4_prefix(prefix)
            return ([addr], [mask])
        else:
            (addr, mask) = get_ipv6_prefix(prefix)
            return (
                [
                    (addr & 0xffffffff000000000000000000000000 ) >> 96,
                    (addr & 0x00000000ffffffff0000000000000000 ) >> 64,
                    (addr & 0x0000000000000000ffffffff00000000 ) >> 32,
                    (addr & 0x000000000000000000000000ffffffff )
                ],
                [
                    (mask & 0xffffffff000000000000000000000000 ) >> 96,
                    (mask & 0x00000000ffffffff0000000000000000 ) >> 64,
                    (mask & 0x0000000000000000ffffffff00000000 ) >> 32,
                    (mask & 0x000000000000000000000000ffffffff )
                ]
            )

    @staticmethod
    def byte_list_to_long(byte_list):
        """ convert byte list (addr_byte or mask_byte) to a long. Note, since ipv4 addr is a single
            entry it can simply be returned. Else assume an ipv6 address and each value is 32 bit
            unsigned value
        """
        result = 0
        for i, x in enumerate(byte_list):
            result = (result << 32) + x
        return result


