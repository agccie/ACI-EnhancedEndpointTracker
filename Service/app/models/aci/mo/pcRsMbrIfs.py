
from ... rest import Rest
from ... rest import api_callback
from ... rest import api_register
from . import ManagedObject

import logging
import re

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="mo/pcRsMbrIfs")
class pcRsMbrIfs(ManagedObject):

    # may not be a reliable subscription, seems to work ok on E+
    TRUST_SUBSCRIPTION = True

    META_ACCESS = ManagedObject.append_meta_access({
        "namespace":"pcRsMbrIfs",
    })

    META = ManagedObject.append_meta({
        "parent": {
            "type": str,
            "description": "parent dn for this object"
        },
        "tSKey": {},            # eth1/8
    })

    @staticmethod
    @api_callback("before_create")
    def before_create(data):
        """ set parent to  based on dn """
        data["parent"] = re.sub("/rsmbrIfs.+", "", data["dn"])
        return data
