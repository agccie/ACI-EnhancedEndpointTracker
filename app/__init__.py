from flask import Flask, g, abort
from flask.ext.pymongo import PyMongo
from flask_login import (LoginManager, login_required, login_user, 
    current_user, logout_user)
from flask import request, make_response, render_template, jsonify
import re

def get_app_config(config_filename="config.py"):
    # returns only the app.config without creating full app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config")
    # pass if unable to load instance file
    try: app.config.from_pyfile(config_filename) 
    except IOError: pass
    # import private config when running in APP_MODE
    try: app.config.from_pyfile("/home/app/config.py", silent=True)
    except IOError: pass
    return app.config

def create_app(config_filename="config.py"):

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config")
    # pass if unable to load instance file
    try: app.config.from_pyfile(config_filename)
    except IOError: pass
    # import private config when running in APP_MODE
    try: app.config.from_pyfile("/home/app/config.py", silent=True)
    except IOError: pass

    # register dependent applications
    app.mongo = PyMongo(app)

    # setup application settings from database
    from .models.settings import Settings
    c = Settings.init_settings(app)
    if c is not None:
        for attr in c:
            app.config[attr] = c[attr]

    # register blueprints
    from .views.api import api
    from .views.auth import auth
    from .views.admin import admin
    from .views.ept import ept
    from .views.base import base
    from .views.doc import doc
    
    app.register_blueprint(base)
    app.register_blueprint(auth) # auth has fixed url_prefix
    app.register_blueprint(api, url_prefix="/api")
    app.register_blueprint(doc, url_prefix="/docs")
    app.register_blueprint(admin, url_prefix="/admin")
    app.register_blueprint(ept, url_prefix="/ept")

    # register error handlers
    register_error_handler(app)
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
            500: "Internal server error",
        }.get(code, "An unknown error occurred")

        # override text description with provided error description
        if error is not None and hasattr(error, "description") and \
            len(error.description)>0:
            text = error.description

        # if error was not from api or proxy then render template, 
        # else return json
        if re.search("/api/", request.url) is None and \
            re.search("/proxy(.json)?$", request.url) is None:
            template = {
                400: "errors/400_invalid_request.html",
                401: "errors/401_unauthorized.html",
                403: "errors/403_forbidden.html",
                404: "errors/404_not_found.html",
                405: "errors/405_method_not_allowed.html",
                500: "errors/500_internal_error.html"
            }.get(code, "errors/500_internal_error.html")
            return render_template(template, description=text), code    
        else:
            return make_response(jsonify({"error":text}), code)

    for code in (400,401,403,404,405,500):
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

    abort(403, " ")

