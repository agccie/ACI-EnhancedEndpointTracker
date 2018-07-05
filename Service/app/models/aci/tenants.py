
import logging
from ..rest import (Rest, api_register)


# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric")
class Tenant(Rest):

    logger = logger
    META_ACCESS = {}

    META = {
        "tenant":{
            "key": True,
            "type":str, 
            "default":"", 
            "key_sn": "tn",
            "regex":"^[a-zA-Z0-9\-\.:_]{1,64}$",
        },
    }

@api_register(path="bd", parent="tenant")
class BridgeDomain(Rest):
    logger = logger
    META = {
        "bd": {
            "key": True,
            "type": str
        },
        "unicastRoute":{
            "type": bool    
        }
    }

