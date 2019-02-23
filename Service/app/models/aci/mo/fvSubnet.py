
from ... rest import Rest
from ... rest import api_register
from ... rest import api_callback
from . import ManagedObject

import logging
import re

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="mo/fvSubnet")
class fvSubnet(ManagedObject):

    META_ACCESS = ManagedObject.append_meta_access({
        "namespace":"fvSubnet",
    })

    META = ManagedObject.append_meta({
        "ip": {},
        "parent": {
            "type": str,
            "description": "parent dn for this object"
        },
        "tCl": {
            "type": str,
            "description": "parent classname (fvBD|fvSvcBD|fvAEPg|vnsEPpInfo|vnsLIfCtx)"
        },
    })

    @staticmethod
    @api_callback("before_create")
    def before_create(data):
        """ set parent to  based on dn 
            applicable parent classnames:
            fvBD:
                uni/tn-{name}/BD-{name}
                uni/tn-{name}/svcBD-{name}
            fvAEPg:
                uni/tn-{name}/ap-{name}/epg-{name}
            vnsEPpInfo:
                uni/tn-{name}/LDevInst-{[priKey]}-ctx-{ctxName}/G-{graphRn}-N-{nodeRn}-C-{connRn}
                uni/vDev-{[priKey]}-tn-{[tnDn]}-ctx-{ctxName}/rndrInfo/eppContr/G-{graphRn}-N-{nodeRn}-C-{connRn}
            vnsLIfCtx:
                uni/tn-{name}/ldevCtx-c-{ctrctNameOrLbl}-g-{graphNameOrLbl}-n-{nodeNameOrLbl}/lIfCtx-c-{connNameOrLbl}
            mgmtInB:
                uni/tn-{name}/mgmtp-{name}/inb-{name}
        """
        data["parent"] = re.sub("/subnet-\[[^]]+\]$", "", data["dn"])
        if "/BD-" in data["parent"]:
            data["tCl"] = "fvBD"
        elif "/svcBD-" in data["parent"]:
            data["tCl"] = "fvSvcBD"
        elif "/ap-" in data["parent"]:
            data["tCl"] = "fvAEPg"
        elif "/LDevInst-" in data["parent"] or "/vDev-" in data["parent"]:
            data["tCl"] = "vnsEPpInfo"
        elif "/ldevCtx-" in data["parent"]:
            data["tCl"] = "vnsLIfCtx"
        elif "/mgmtp-" in data["parent"]:
            data["tCl"] = "mgmtInB"
        else:
            logger.warn("failed to map parent class (tCl) for fvSubnet: %s", data["dn"])
        return data

