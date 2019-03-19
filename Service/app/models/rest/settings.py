
from . import Rest
from . import Role
from . import api_register
import logging

@api_register()
class Settings(Rest):
    """ Global application settings that can be used only in standalone mode """

    # allow only read and update requests
    META_ACCESS = {
        "create": False,
        "delete": False,
        "bulk_update": True,    # no keys or _id requires bulk update
        "default_role": Role.FULL_ADMIN,
        "keyed_path": False,
        "dn": False,
    }

    META = {
        "app_name": {
            "type":str, 
            "default":"AppName",
            "regex": "^(?i).{1,128}$",  # any 128 character string
            "description": "application name",
        },
        "password_reset_timeout": {
            "type": int, 
            "description": "timeout in seconds for password reset key",
            "default": 86400,       # 1 day
            "min": 60,
            "max": 31536000,        # 1 year
        },
        "password_strength_check": {
            "type":bool, 
            "default":False, 
            "description": "enable password strength check",
        },
        "session_timeout": {
            "type": int,
            "description": "maximum session length in seconds",
            "default": 86400,       # 1 day
            "min": 60,
            "max": 31536000,        # 1 year
        },
        "smtp_type": {
            "type": str,
            "values": ["direct", "relay"],
            "default": "direct",
            "description": """ send SMTP directly to email receipent based on MX records of address
                or relay through configured smtp_relay server with optional login credentials
                """
        },
        "smtp_relay_server": {
            "type": str,
            "default": "",
            "regex": "(?i)^[a-z0-9_\.:\-]{0,512}$",
            "description": """ SMTP relay server """,
        },
        "smtp_relay_server_port": {
            "type": int,
            "default": 587,
            "description": """ SMTP relay server port. Port 25 is often used for standard SMTP and 
                port 456 and 587 used for SSL/TLS, respectively. This app will always try to 
                negotiate TLS even if running on port 25.
                """,
        },
        "smtp_relay_authenticate": {
            "type": bool,
            "default": False,
            "description": "enable authentication for SMTP relay",
        },
        "smtp_relay_username": {
            "type": str,
            "default": "",
            "regex": "^[^ ;]{0,512}$",
            "description": "SMTP relay username or email address used for relay authentication",
        },
        "smtp_relay_password": {
            "type": str,
            "default": "",
            "encrypt": True,
            "read": False,
            "regex": "^.{0,512}$",
            "description": "SMTP relay password used for relay authentication",
        },
        # cached smtp domain or server with lifetime to prevent excessive calls
        "smtp_cached_record": {
            "type": dict,
            "read": True,
            "write": False,
            "meta": {
                # cache exchange hostname for a particular domain
                "domain": {
                    "type": dict,
                    "meta": {
                        "domain": { "type": str },
                        "exchange": { "type": str },
                        "ttl": {"type": float },
                    },
                },
                # cache single server which could be hostname from exchange or relay server info
                "server": {
                    "type": dict,
                    "meta": {
                        "hostname": { "type": str },
                        "ip": { "type": str },
                        "ttl": { "type": float },
                    },
                }
            },
        },
        # encrypted local user password for backend API calls
        "lpass": {
            "type":str,
            "encrypt": True,
            "read":False,
            "write":False,
            "description": "local user password set at application initialization",
        },
    }

