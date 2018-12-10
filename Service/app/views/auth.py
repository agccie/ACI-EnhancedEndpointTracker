from flask import current_app, Blueprint

auth_prefix = "/auth"
auth = Blueprint("auth", __name__, url_prefix=auth_prefix)

from flask import g, abort
from flask_login import (LoginManager, current_user)

from ..models.rest.user import User, Session
from ..models.rest import Role
from ..models.utils import MSG_403
import logging

logger = logging.getLogger(__name__)

# setup login manager
login_manager = LoginManager()


# since this is a blueprint, use record_once instead of login_manager.init_app
@auth.record_once
def on_load(state):
    login_manager.login_view = "%s/login/" % auth_prefix
    login_manager.login_message = ""
    login_manager.init_app(state.app)


@auth.before_app_request
def before_request():
    # set global object 'g.user' based off current user session
    g.ROLE_FULL_ADMIN = Role.FULL_ADMIN
    g.user = current_user
    if g.user is not None:
        if hasattr(g.user, 'role') and g.user.role == Role.BLACKLIST:
            User.logout()
            abort(403, MSG_403)
        elif not current_app.config.get("LOGIN_ENABLED", True) and \
                not g.user.is_authenticated:
            # auto-login user as local if login is disabled
            g.user = Session(username="local", role=Role.FULL_ADMIN)


@login_manager.user_loader
def load_user(session):
    return Session.load_session(session)
