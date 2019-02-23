
from ... rest import Rest
from ... rest import api_register
from . import ManagedObject

import logging

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="mo/pcAggrIf")
class pcAggrIf(ManagedObject):

    # pcAggrIf may not be a reliable subscription, seems to work ok on E+
    TRUST_SUBSCRIPTION = True

    META_ACCESS = ManagedObject.append_meta_access({
        "namespace":"pcAggrIf",
    })

    META = ManagedObject.append_meta({
        "id": {},       # po4
        "name": {},     # ag_po2002
    })

