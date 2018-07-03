
import logging
from ..rest import (Rest, api_register)


# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric")
class Tenant(Rest):

    logger = logger

    META = {
        "tenant":{
            "key": True,
            "type":str, 
            "default":"", 
            "key_sn": "tn",
            "regex":"^[a-zA-Z0-9\-\.:_]{1,64}$",
        },
    }

