from flask import Flask, g, abort
from flask_login import (LoginManager, login_required, login_user, 
    current_user, logout_user)
from flask import request, make_response, render_template, jsonify
import re

def create_app_config(config_filename="config.py"):
    # get app config without initiating entire app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config")
    # pass if unable to load instance file
    try: app.config.from_pyfile(config_filename)
    except IOError: pass
    # import private config when running in APP_MODE
    try: app.config.from_pyfile("/home/app/config.py", silent=True)
    except IOError: pass
    return app.config

_app = None
def create_app(config_filename="config.py"):
    global _app
    if _app is not None: return _app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config")
    # pass if unable to load instance file
    try: app.config.from_pyfile(config_filename)
    except IOError: pass
    # import private config when running in APP_MODE
    try: app.config.from_pyfile("/home/app/config.py", silent=True)
    except IOError: pass

    # add custom converter (filename) so attribute keys can be type 'filename'
    app.url_map.converters["filename"] = FilenameConverter

    # import model objects (which auto-register with api)
    from .models.aci.fabric import Fabric
    from .models.app_status import AppStatus
    from .models.rest.swagger.docs import Docs
    from .models.settings import Settings
    from .models.user import User

    # ept objects
    from .models.aci.ept.history import eptHistory
    from .models.aci.ept.move import eptMove
    from .models.aci.ept.node import eptNode
    from .models.aci.ept.offsubnet import eptOffSubnet
    from .models.aci.ept.settings import eptSettings
    from .models.aci.ept.stale import eptStale
    from .models.aci.ept.tunnel import eptTunnel
    from .models.aci.ept.vnid import eptVnid

    # auto-register api objects
    from .views.api import api
    from .models.rest import register
    register(api)

    # register blueprints
    from .views.auth import auth
    from .views.base import base
    from .views.doc import doc
    app.register_blueprint(base)
    app.register_blueprint(auth) # auth has fixed url_prefix
    app.register_blueprint(api, url_prefix="/api")
    app.register_blueprint(doc, url_prefix="/docs")

    # register error handlers
    register_error_handler(app)
    
    # if cors is enabled, add to entire app
    if app.config.get("ENABLE_CORS", False):
        from flask_cors import CORS
        CORS(app, supports_credentials=True, automatic_options=True)

    _app = app
    return app


def register_error_handler(app):    
    """ register error handler's for common error codes to app """
    def error_handler(error):
        code = getattr(error, "code", 500)
        # default text for error code
        text = {
            400: "Invalid Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "URL not found",
            405: "Method not allowed",
            413: "Filesize or request is too large",
            500: "Internal server error",
            503: "Service unavailable",
        }.get(code, "An unknown error occurred")

        # override text description with provided error description
        if error is not None and hasattr(error, "description") and \
            len(error.description)>0:
            text = error.description

        # return json for all errors for now...
        return make_response(jsonify({"error":text}), code)

    for code in (400,401,403,404,405,413,500,503):
        app.errorhandler(code)(error_handler)

    return None

def basic_auth():
    """ basic authentication that can be provided to admin-only blueprints
        that aborts on error else returns None
    """
    g.user = current_user
    if g.user is not None:
        if hasattr(g.user, "is_authenticated") and hasattr(g.user, "role"):
            if g.user.is_authenticated and g.user.role == g.ROLE_FULL_ADMIN:
                return
    abort(403, "")

from werkzeug.routing import BaseConverter
class FilenameConverter(BaseConverter):
    """ support filename which can be any character of arbitrary length """
    regex = ".*?"

