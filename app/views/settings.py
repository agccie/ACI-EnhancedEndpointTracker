
from flask import current_app, Blueprint, render_template
settings = Blueprint("settings", __name__)

from flask import Flask, jsonify, redirect, url_for
from flask import request, make_response, g, abort
from flask_login import (login_required, current_user)

from ..models.users import Users
from ..models.roles import Roles

@settings.route("/")
@login_required
def settings():
    # ensure user is full admin
    if g.user.role != Roles.FULL_ADMIN: abort(403)
    return render_template("settings.html")

