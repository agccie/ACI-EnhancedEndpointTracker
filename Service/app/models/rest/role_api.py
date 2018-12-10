import logging

from flask import current_app
from flask import jsonify

from . import Rest
from . import api_register
from . import api_route
from .role import Role

# module level logging
logger = logging.getLogger(__name__)


# expose an API to get roles
@api_register(path="/role")
class RoleApi(Rest):
    logger = logger
    META_ACCESS = {
        "create": False,
        "read": False,
        "update": False,
        "delete": False,
    }
    META = {}

    @staticmethod
    @api_route(path="/", methods=["GET"])
    def read_roles():
        """ get mapping of role value to role name """
        return jsonify(Role.ROLES_STR)

    @staticmethod
    @api_route(path="/routes", methods=["GET"])
    def get_urls():
        """ get all available app routes """
        from ..utils import list_routes
        return jsonify(list_routes(current_app, api=True))
