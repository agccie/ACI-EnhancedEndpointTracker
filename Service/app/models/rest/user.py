
from . import Rest
from . import Role
from . import api_register
from . import api_route
from . import api_callback
from ..utils import get_user_data
from ..utils import get_user_params 
from ..utils import get_user_headers 
from ..utils import get_user_cookies
from .settings import Settings

from flask import abort
from flask import g
from flask import current_app
from flask import jsonify

import base64
import json
import logging
import os
import time
import uuid

# module level logger
logger = logging.getLogger(__name__)

@api_register()
class User(Rest):
    """ Local user object for authentication and authorization when running in standalone mode. """

    logger = logger

    # reserved usernames
    RESERVED = [ "root", "local" ]

    META_ACCESS = {
        "create_role": Role.FULL_ADMIN,
        "read_role": Role.USER,
        "update_role": Role.USER,
        "delete_role": Role.FULL_ADMIN,
    }

    # meta data and type that are exposed via read/write with type and defaults
    META = {
        "username":{
            "key": True,
            "type": str,
            "regex": "^(?i)[a-z0-9\_.:]{1,128}$",
            "default": "",
            "description": "user username",
        },
        "password": {
            "type": str,
            "regex": "^.{1,256}$",
            "hash": True,
            "read": False,
            "default": "password",
            "description": "user password",
        },
        "role": {
            "type": int,
            "default": Role.USER,
            "min": Role.MIN_ROLE,
            "max": Role.MAX_ROLE,
            "description": "user role used for role-based authentication",
        },
        "last_login": {
            "type": float,
            "write": False,
            "description": "epoch timestamp of last successful login event for this user",
        },
        "password_reset_key": {
            "type": str,
            "read": False,
            "write": False,
            "description": "temporary password reset key",
        },
        "password_reset_timestamp": {
            "type": float,
            "read": False,
            "write": False,
            "description": "epoc timestamp when password_reset_key was issued",
        },
        # reference for swagger only
        "token_required": {
            "reference": True,
            "type": bool,
            "default": False,
            "description": "used by login API to indicate that CSFR token is required",
        },
        "token": {
            "reference": True,
            "type": str,
            "default": "",
            "description": "CSFR token which will be required in each session request",
        },
    }

    @staticmethod
    @api_route(path="logout", methods=["POST"], role=Role.USER)
    def logout():
        """ logout current user """
        session_id = Session.load_session()
        if session_id is not None:
            s = Session.find(session=session_id)
            if len(s)>0:
                #logger.debug("deleting session: %s", session_id)
                s[0].remove()
        # delete session cookie
        ret = User.api_ok()
        ret.set_cookie("session","", max_age=0)
        return ret

    @staticmethod
    @api_route(path="login", methods=["POST"], authenticated=False, swag_ret=["success","token"])
    def login(username, password, token_required=False):
        """ create new user login session """
        u = User.load(username=username)
        if u.exists():
            from flask_bcrypt import check_password_hash
            try:
                if check_password_hash(u.password, password):
                    u.last_login = time.time()
                    u.save()
                    # create a new session for user
                    sid = base64.b64encode(os.urandom(64))
                    s = Session(username=u.username, session=sid, token_required=token_required)
                    if not s.save():
                        logger.error("failed to create session for user %s", u.username)
                    js = {
                        "success": True,
                        "token": "",
                        "session": sid
                    }
                    if token_required:
                        js["token"] = s.token
                    # set session cookie on response
                    ret = jsonify(js)
                    ret.set_cookie("session", s.session)
                    return ret
            except Exception as e:
                logger.error("check_password_hash failed: %s", e)
        else:
            logger.debug("username %s does not exist", username)
        abort(401, "Authentication Failed")

    @api_route(path="pwreset", methods=["GET"], role=Role.USER)
    def get_password_reset_key(self):
        """ get a temporary password reset link for user. The reset link can only be requested by 
            users with admin privilege or for the current authenticated user
        """
        # non-admins can only get a pwreset link for thier account
        if g.user.role != Role.FULL_ADMIN and self.username != g.user.username:
            abort(403)

        # create a temporary random key and timestamp it
        self.password_reset_key = "%s"%uuid.uuid4()
        self.password_reset_timestamp = time.time()
        self.save()
        return jsonify({"key": self.password_reset_key})

    @staticmethod
    @api_route(path="pwreset", methods=["POST"], authenticated=False)
    def password_reset(username, password, password_reset_key):
        """ request to reset user password """
        u = User.load(username=username)
        if not u.exists():
            abort(400, "Incorrect username or inactive key provided")

        # ensure provided key is correct and still valid
        if u.password_reset_key != password_reset_key:
            abort(400, "Incorrect username or inactive key provided")

        pwtimeout = int(current_app.config.get("password_reset_timeout", 7200))
        if u.password_reset_timestamp+pwtimeout < int(time.time()):
            # key has timed out, reset it and return an error
            u.password_reset_timestamp = 0
            u.password_reset_key = ""
            u.save()
            abort(400, "Incorrect username or inactive key provided")

        # ok to update password
        u.password = password
        u.password_reset_timestamp = 0
        u.password_reset_key = ""
        u.save()
        return User.api_ok()

    @classmethod
    @api_callback("before_create")
    def before_user_create(cls, data, api=False):
        # only perform check on api calls
        if not api: return data
        # ensure username is not a reserved username
        if "username" in data and data["username"] in User.RESERVED:
            abort(400, "Username \"%s\" is reserved" % data["username"])
        return data

    @classmethod
    @api_callback("before_read")
    def before_user_read(cls, filters, api=False):
        # only perform check on api calls
        if not api: return filters
        # for non-admins, force filter to include their username
        admin = (g.user.role == Role.FULL_ADMIN)
        if not admin:
            if "username" in filters:
                if filters["username"] != g.user.username:
                    abort(403)
            else:
                filters["username"] = g.user.username
        return filters

    @classmethod
    @api_callback("before_update")
    def before_user_update(cls, filters, data, api=False):
        # only perform check on api calls
        if not api: return (filters, data)
        # block user from updating reserved users
        admin = (g.user.role == Role.FULL_ADMIN)
        if "username" in filters:
            if filters["username"] in User.RESERVED:
                abort(400, "Username \"%s\" is reserved and cannot be updated"%filters["username"])
            elif not admin and g.user.username != filters["username"]:
                abort(403)
        else:
            if not admin:
                # for non-admin users, filter must include their username
                filters["username"] = g.user.username
            else:
                # else add filter blocking updates to reserved usernames
                filters["username"] = {"$nin":User.RESERVED}

        # block role elevation
        if filters["username"] == g.user.username:
            if "role" in data and data["role"]!=g.user.role:
                abort(403, "cannot modify local user role")

        return (filters, data)

    @classmethod
    @api_callback("before_delete")
    def before_user_delete(cls, filters, api=False):
        # only perform check on api calls
        if not api: return filters
        username = g.user.username
        if "username" in filters:
            if filters["username"] in User.RESERVED:
                abort(400, "Username \"%s\" is reserved and cannot be updated"%filters["username"])
            elif username is not None and username == filters["username"]:
                abort(400, "User \"%s\" cannot delete user \"%s\""%(username, filters["username"]))
        else:
            # else add filter blocking updates to reserved usernames and local user
            filters["username"] = {"$nin":User.RESERVED}
            if username is not None: filters["username"]["$nin"].append(username)
        return filters

    @classmethod
    @api_callback("after_read")
    def after_user_read(cls, data, api=False):
        # only perform check on api calls.  
        if not api: return data
        # remove reserved usernames from results
        if "objects" not in data or "count" not in data: return data
        count = data["count"]
        objects = []
        for o in data["objects"]:
            if "username" in o["user"] and o["user"]["username"] in User.RESERVED:
                count-= 1
            else: objects.append(o)
        if count < 0: count = 0
        return {"count": count, "objects": objects}

@api_register(parent="user")
class Session(Rest):
    logger = logger
    META_ACCESS = {
        "create": False,
        "read": False,
        "update": False,
        "delete": False,
        "doc_enable": False,
    }
    META = {
        "session": {
            "type": str,
            "key": True,
            "description": "unique session id",
        },
        "created": {
            "type": float,
            "description": "epoch timestampe when session was created",
        },  
        "timeout": {
            "type": float,
            "description": "epoch timestamp when session will no longer be valid",
        },
        "token_required": {
            "type": bool,
            "default": False,
            "description": "csfr token enabled for session authentication",
        },
        "token": {
            "type": str,
            "description": "csfr token"
        },
    }

    @staticmethod
    def load_session():
        """ load session id from auth header or cookie and return value.  
            Return None if not found 
        """
        # need to get the session_id from the header (preferred) or cookie
        session_id = get_user_headers().get("session", None)
        if session_id is None:
            return get_user_cookies().get("session", None)
        return session_id

    @staticmethod 
    def load_user():
        """ load user object from session id in cookie or header. If session is invalid return None
            else return valid user
        """
        session_id = Session.load_session()
        if session_id is None:
            return None

        # load user object for corresponding session id.  If session id is invalid, has expired,
        # or token is not present within the request and token_required enabled, then return None
        now = time.time()
        s = Session.find(session=session_id)
        if len(s)== 0: 
            return None
        else:
            s = s[0]
        if now > s.timeout:
            logger.debug("session %s timeout (%s > %s)", s.session, now, s.timeout)
            return None
        # perform CSFR check if token_required 
        if s.token_required:
            # accept token only in header
            token = get_user_headers().get("app-token", None)
            #if token is None:
            #    token = get_user_data().get("app_token", None)
            #if token is None:
            #    token = get_user_params().get("app_token", None)
            if token is None:
                logger.debug("no token provided for session %s", s.session)
                return None
            if token != s.token:
                logger.debug("invalid token %s provided for session %s", token, s.session)
                return None

        # load user corresponding to valid session
        u = User.load(username=s.username)
        if not u.exists(): 
            logger.debug("username %s for session %s no longer exists", s.username, s.session)
            return None
        #logger.debug("user %s, session %s", u.username, s.session)
        return u

    @classmethod
    @api_callback("before_create")
    def before_session_create(cls, data):
        # allocate session value and token if token_required and set session timeout
        # urandom used for session id's and uuid4 used for csfr tokens
        now = time.time()
        s = Settings.load()
        data["created"] = now
        data["timeout"] = s.session_timeout + now
        if data["token_required"]:
            data["token"] = base64.b64encode("%s" % uuid.uuid4())
        return data

    @classmethod
    @api_callback("after_create")
    def after_session_create(cls, data):
        # after each successful session creation, purge expired sessions
        ret = Session.delete(_filters={"session":{"$lte":time.time()}})    
        if "count" in ret and ret["count"]>0:
            logger.debug("old sessions purged: %s", ret["count"])
        s = Session.load(username=data["username"], session=data["session"])
        if not s.exists():
            logger.debug("failed to save that session thing...")
        else:
            logger.debug("created session: (%s, %s, token:%s, timeout: %s)", s.username, s.session,
                    s.token, s.timeout)

