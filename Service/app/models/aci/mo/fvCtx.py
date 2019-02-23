
from ... rest import Rest
from ... rest import api_register
from . import ManagedObject

import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="mo/fvCtx")
class fvCtx(ManagedObject):

    META_ACCESS = ManagedObject.append_meta_access({
        "namespace":"fvCtx",
    })

    META = ManagedObject.append_meta({
        "pcTag": {},
        "scope": {},
    })

