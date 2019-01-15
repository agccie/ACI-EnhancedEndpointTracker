
from .. models.rest.user import User
from .. models.rest.user import Session
from .. models.rest import Role
from .. models.utils import MSG_403
from flask import abort
from flask import current_app
from flask import g
from flask import Blueprint
import logging

logger = logging.getLogger(__name__)

auth_prefix = "/auth"
auth = Blueprint("auth", __name__, url_prefix=auth_prefix)

@auth.before_app_request
def before_request():
    """ load user session or default anonymous/unauthenticated user """
    g.ROLE_FULL_ADMIN = Role.FULL_ADMIN
    if current_app.config.get("LOGIN_ENABLED", True):
        g.user = Session.load_user()
        if g.user is None:
            # create a User with is_authenticated set to false
            g.user = User(username="anonymous")
            setattr(g.user, "is_authenticated", False)
        else:
            setattr(g.user, "is_authenticated", True)
    else:
        # login disabled, set the user to unconditionally to local
        g.user = User(username="local", role=Role.FULL_ADMIN)
        setattr(g.user, "is_authenticated", True)

    # block blacklist user
    if g.user.role == Role.BLACKLIST:
        abort(403, MSG_403)

