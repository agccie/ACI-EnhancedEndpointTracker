
from flask import current_app, Blueprint, render_template
auth_prefix = "/auth"
auth = Blueprint("auth", __name__, url_prefix=auth_prefix)

from flask import Flask, jsonify, flash, redirect, url_for
from flask import request, make_response, g, url_for, abort, session
from flask_login import (LoginManager, login_required, login_user,
    current_user, logout_user)

from ..models.users import Users
from ..models.roles import Roles
from ..models.utils import MSG_403

# setup login manager
login_manager = LoginManager()

# since this is a blueprint, use record_once instead of login_manager.init_app
@auth.record_once
def on_load(state):
    # setup login manager login_view
    if state.app.config.get("SSO_ENABLED", False):
        # url_for not available at this point 
        login_manager.login_view = "%s/sso/" % auth_prefix
    else:
        # url_for not available at this point 
        login_manager.login_view = "%s/login/" % auth_prefix
    login_manager.login_message = ""
    login_manager.init_app(state.app)

@auth.before_app_request
def before_request():
    # force everything over HTTPS if enabled
    if current_app.config.get("force_https", False):
        fwd_proto = request.headers.get("x-forwarded-proto",None)
        if fwd_proto is not None:
            if fwd_proto.lower() == "http":
                return redirect(request.url.replace("http:","https:", 1))
        else:
            if re.search("^http:", request.url) is not None:
                return redirect(request.url.replace("http:","https:", 1))

    # set global object various configs
    g.app_name = current_app.config.get("app_name", "AppName1")

    # set global object 'g.user' based off current user session
    g.ROLE_FULL_ADMIN = Roles.FULL_ADMIN
    g.user = current_user
    if g.user is not None:
        if hasattr(g.user, 'role') and g.user.role == Roles.BLACKLIST:
            Users.logout()
            abort(403, MSG_403)
        elif not current_app.config.get("LOGIN_ENABLED", True) and \
            not g.user.is_authenticated:
            # auto-login user as admin if login is disabled
            g.user = Users.load_user("admin")
            if g.user is None:
                # manually add user to database if not previously present
                g.user = Users({"username":"admin", "role": Roles.FULL_ADMIN,
                    "password":"cisco"})
                g.user._auto_create()
            Users.start_session("admin")

@login_manager.user_loader
def load_user(username):
    return Users.load_user(username)

@auth.route("/login", methods=["GET", "POST"])
@auth.route("/login/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if Users.login(
            username = request.form['username'],
            password = request.form['password'],
            remember = True):
            return redirect(request.args.get("next") or "/")
        else:
            flash("The email or password you entered is incorrect.")
            return render_template("auth/login.html")

    return render_template("auth/login.html")

@auth.route("/logout")
@auth.route("/logout/")
def logout():
    Users.logout()
    return render_template("auth/logout.html")

@auth.route("/pwreset/<string:key>", methods=["GET"])
def pwreset(key):
    return render_template("auth/pwreset.html", key=key)

##############################################################################
# Auth API, imported by api module
##############################################################################

def api_login():
    """ login to application and create session cookie.  Note, if sso
        authentication is enabled, then this function is not required. Simply
        provided the sso cookie and the application will authenticate it.
        Args:
            username(str): application username
            password(str): application password
        Returns:
            success(bool): successfully login
    """
    data = request.json
    if not data: abort(400, "Invalid JSON provided")
    if "username" not in data:
        abort(400, "Required parameter \"username\" not provided")
    if "password" not in data:
        abort(400, "Required parameter \"password\" not provided")

    if Users.login(
        username = data["username"],
        password = data["password"],
        remember = True):
        return jsonify({"success": True})
    else:
        abort(401, "Authentication Failed")

def api_logout():
    """ logout of application and delete session """
    Users.logout()
    return jsonify({"success": True})


##############################################################################
# 
#   Cisco SSO handlers
#
##############################################################################

import re, requests

@auth.route("/sso", methods=["GET"])
@auth.route("/sso/", methods=["GET"])
def sso_login():
    """
    use sso_handler to check if user is already authenticated.  If not,
    redirect user to sso_url with referer set to /rsso (return sso) and next
    argument set to original provided parameter.  If user is authenticated,
    login user locally to site and redirect to page at next argument
    """
    if not current_app.config.get("SSO_ENABLED", False):
        abort(400, "SSO authentication not enabled")

    if len(current_app.config.get("sso_url",""))<=0:
        abort(500, "sso_url not defined in app.config")
    if len(current_app.config.get("fqdn",""))<=0:
        abort(500, "fqdn not defined in app.config")

    # not implemented, force fail
    return render_template("auth/sso_failed.html")


@auth.route("/rsso", methods=["GET"])
@auth.route("/rsso/", methods=["GET"])
def sso_login_return():
    """
    this page is redirected to after user has completed authentication on
    SSO site. If username is valid, redirect to 'next' parameter, else display
    sso_failed page
    """
    if not current_app.config.get("SSO_ENABLED", False):
        abort(400, "SSO authentication not enabled")

    # not implemented, force fail
    return render_template("auth/sso_failed.html")


