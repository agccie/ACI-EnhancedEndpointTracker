
from flask import request, abort, g, current_app
from utils import (get_user_data, MSG_403)
from pymongo.errors import DuplicateKeyError
import logging

from .roles import Roles
from .users import Users
from .rest import Rest

class Settings(Rest):

    # meta data and type that are exposed via read with type and default values
    META = {
        "app_name":     {"type":str, "default":"AppName", "read":True, 
                        "write":True},
        "force_https":  {"type": bool, "default": False, "read":True, 
                        "write":True},
        "fqdn":         {"type":str, "default":"", "read":True, "write":True},
        "sso_url":      {"type":str, "default":"", "read":True, "write":True},
        "pw_reset_timeout": {"type": int, "default": 86400, "read":True,
                        "write":True},
    }

    def __init__(self):
        super(Rest, self).__init__()

    @staticmethod
    def init_settings(app):
        """ builds settings object based on database values. Used during 
            initial load of application
        """
        with app.app_context():
            current_app = app
            # setup g.user object as root user
            g.user = Users({
                "username": "root",
                "role": Roles.FULL_ADMIN
            })
            # support abort for read error (return no value)
            try:
                return Settings.read(su_read=True)
            except Exception as e:
                pass
            return {}

    @classmethod
    def create(cls):
        """ block create requests to settings (not implemented) """
        abort(400, "cannot create new settings entry")

    @classmethod
    def read(cls, su_read=False):
        """ api call - read settings from database 
            set su_readd to True to allow su access
        """

        r = Rest.read.__func__(cls, current_app.mongo.db.settings,
            rule_dn = "/config/",
            su = su_read
        )

        if len(r["settings"])<=0: abort(404, "No settings in database")
        return r["settings"][0]

    @classmethod
    def update(cls):
        """ api call - update global settings """

        # perform update (aborts on error)
        return Rest.update.__func__(cls, current_app.mongo.db.settings,
            rule_dn = "/config/",
            update_many = {},
        )

    @classmethod
    def delete(cls):
        """ block delete requests to settings (not implemented) """
        abort(400, "cannot delete settings")

