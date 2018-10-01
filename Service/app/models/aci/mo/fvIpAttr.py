
from ... rest import Rest
from ... rest import api_register
from ... rest import api_callback
from . import ManagedObject

import logging
import re

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="mo/fvIpAttr")
class fvIpAttr(ManagedObject):

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
        data["parent"] = re.sub("/crtrn/ipattr-.+$","", data["dn"])
        return data
