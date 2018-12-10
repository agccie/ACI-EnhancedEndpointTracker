import logging
import re

from . import ManagedObject
from ...rest import api_callback
from ...rest import api_register

# module level logging
logger = logging.getLogger(__name__)


@api_register(parent="fabric", path="mo/fvIpAttr")
class fvIpAttr(ManagedObject):
    META_ACCESS = ManagedObject.append_meta_access({
        "namespace": "fvIpAttr",
    })

    META = ManagedObject.append_meta({
        "ip": {},
        "usefvSubnet": {},
        "parent": {
            "type": str,
            "description": "parent fvAEPg dn"
        },
    })

    @staticmethod
    @api_callback("before_create")
    def before_create(data):
        """ set parent based on dn """
        data["parent"] = re.sub("/crtrn/ipattr-.+$", "", data["dn"])
        return data
