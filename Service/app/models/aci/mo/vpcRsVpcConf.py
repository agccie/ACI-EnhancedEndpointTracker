
from ... rest import Rest
from ... rest import api_register
from . import ManagedObject

import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="mo/vpcRsVpcConf")
class vpcRsVpcConf(ManagedObject):

    # vpcRsVpcConf is not a reliable subscription
    TRUST_SUBSCRIPTION = True   

    META = ManagedObject.append_meta({
        "tSKey": {},
        "parentSKey": {},
    })
