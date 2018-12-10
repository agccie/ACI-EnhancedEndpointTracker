import logging

from . import ManagedObject
from ...rest import api_register

# module level logging
logger = logging.getLogger(__name__)


@api_register(parent="fabric", path="mo/vpcRsVpcConf")
class vpcRsVpcConf(ManagedObject):
    # vpcRsVpcConf is not reliable, arbitrary deletes 10 seconds after create (CSCvm84902)
    TRUST_SUBSCRIPTION = False

    META_ACCESS = ManagedObject.append_meta_access({
        "namespace": "vpcRsVpcConf",
    })

    META = ManagedObject.append_meta({
        "tSKey": {},
        "parentSKey": {},
    })
