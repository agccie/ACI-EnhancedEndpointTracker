
import logging
from .rest import (Rest, api_register)
from .role import api_read_roles
from flask import jsonify

# module level logging
logger = logging.getLogger(__name__)

def verify_urls():
    """ get urls successfully registered with flask routing module.  Note,
        this has nothing to do with 'roles' but just a convenient url
        endpoint for now...
    """
    from ..utils import list_routes
    from flask import current_app
    return jsonify(list_routes(current_app, api=True))

# expose an API to get roles 
@api_register(path="/role")
class RoleApi(Rest):
    logger = logger
    META_ACCESS = {
        "create": False,
        "read": False,
        "update": False,
        "delete": False,
        "routes": [
            {
                "path":"/", 
                "methods":["GET"], 
                "function": api_read_roles,
                "summary": "get mapping of role value to role name"
            },
            {
                "path": "/routes",
                "methods": ["GET"],
                "function": verify_urls,
            }
        ]
    }
    META = {}
