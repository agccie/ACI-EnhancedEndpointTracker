
import logging
from .rest import (Rest, api_register)

@api_register()
class Settings(Rest):

    # allow only read and update requests
    META_ACCESS = {
        "create": False,
        "delete": False,
    }

    META = {
        "app_name": {
            "type":str, 
            "default":"AppName",
            "regex": "^(?i).{1,128}$",  # any 128 character string
        },
        "force_https":  {
            "type": bool, 
            "default": False,
        },
        "password_reset_timeout": {
            "type": int, 
            "default": 86400,       # 1 day
            "min": 5,
            "max": 31536000,        # 1 year
        },
        "password_strength_check": {
            "type":bool, 
            "default":False, 
        },
        # encrypted local user password for backend API calls
        "lpass": {
            "type":str,
            "encrypt": True,
            "read":False,
            "write":False,
        },
    }

