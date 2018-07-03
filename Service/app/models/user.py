
from flask import abort, g, current_app, jsonify
from flask_login import (login_user, logout_user)
from utils import  MSG_403
import uuid, time, json, logging

from .rest import Role
from .rest import (Rest, api_register)
from .utils import get_user_data

# module level logger
logger = logging.getLogger(__name__)

def before_create(data, **kwargs):
    # only perform check on api calls
    if not kwargs.get("_api", False): return data
    # ensure username is not a reserved username
    if "username" in data and data["username"] in User.RESERVED:
        abort(400, "Username \"%s\" is reserved" % data["username"])
    return data

def after_read(results, **kwargs):
    # only perform check on api calls
    if not kwargs.get("_api", False): return results
    # remove reserved usernames from results
    if "objects" not in results or "count" not in results: return results
    count = results["count"]
    objects = []
    for o in results["objects"]:
        if "username" in o["user"] and o["user"]["username"] in User.RESERVED:
            count-= 1
        else: objects.append(o)
    if count < 0: count = 0
    return {"count": count, "objects": objects}

def before_update(filters, update, **kwargs):
    # only perform check on api calls
    if not kwargs.get("_api", False): return (filters, update)

    # block user from updating reserved users
    admin = (g.user.role == Role.FULL_ADMIN)
    if "username" in filters:
        if filters["username"] in User.RESERVED:
            abort(400, "Username \"%s\" is reserved and cannot be updated" %(
                filters["username"]))
        elif not admin and g.user.username != filters["username"]:
            abort(403, MSG_403)
    else:
        if not admin:
            # for non-admin users, filter must include their username
            filters["username"] = g.user.username
        else:
            # else add filter blocking updates to reserved usernames
            filters["username"] = {"$nin":User.RESERVED}
    return (filters, update)

def before_delete(filters, **kwargs):
    # only perform check on api calls
    if not kwargs.get("_api", False): return filters

    # block user from deleting reserved users or deleting themself
    admin = (g.user.role == Role.FULL_ADMIN)
    if not admin: abort(403, MSG_403)
    username = g.user.username
    if "username" in filters:
        if filters["username"] in User.RESERVED:
            abort(400, "Username \"%s\" is reserved and cannot be updated" %(
                filters["username"]))
        elif username is not None and username == filters["username"]:
            abort(400, "User \"%s\" cannot delete user \"%s\"" % (
                filters["username"], filters["username"]))
    else:
        # else add filter blocking updates to reserved usernames and local user
        filters["username"] = {"$nin":User.RESERVED}
        if username is not None: filters["username"]["$nin"].append(username)
    return filters

def api_logout():
    """ logout current user """
    logout_user()
    return jsonify({"success": True})

def api_login():
    """ login to application and create session cookie.  
        Args:
            username(str): application username
            password(str): application password
        Returns:
            success(bool): successfully login
    """
    data = get_user_data()
    if not data: abort(400, "Invalid JSON provided")
    if "username" not in data:
        abort(400, "Required parameter \"username\" not provided")
    if "password" not in data:
        abort(400, "Required parameter \"password\" not provided")

    if User.login(username = data["username"],password = data["password"]):
        return jsonify({"success": True})
    else:
        abort(401, "Authentication Failed")

def api_get_password_reset_key(username):
    """ get a temporary password reset link for user. The reset link can only
        be requested by users with admin privilege or for current_user's
        username

        Returns:
            key(str): password reset key
    """
    User.authorized() 
    key = User.get_password_reset_key(username)
    return jsonify({
        "key": "%s" % key
    })

def api_password_reset():
    """ reset user password

        Args:
            username(str): username
            password(str): new password for user
            password_reset_key(str): password reset key for user

        Returns:
            success(bool): successfully updated
    """
    # only allowed non-authenticated request
    data = get_user_data()
    for a in ["username", "password", "password_reset_key"]:
        if a not in data:
            abort(400, "missing required attribute %s" % a)
    User.password_reset(data["username"], data["password"], 
        data["password_reset_key"])

    # no error implies successful reset
    return jsonify({"success": True}) 

def setup_local(app):
    """ setup local user - creates a random password and adds as encrypted
        value to settings and adds 'local' user to users database
    """
    from .settings import Settings
    lpass = "%s"%uuid.uuid4()
    with app.app_context():
        u = User(username="local", role=Role.FULL_ADMIN)
        u.password = lpass
        u.save()
        s = Settings()
        s.lpass = lpass
        s.save()

@api_register()
class User(Rest):

    logger = logger

    # reserved usernames
    RESERVED = [ "root", "local" ]

    META_ACCESS = {
        "write": Role.USER,
        "before_create": before_create,
        "before_update": before_update,
        "before_delete": before_delete,
        "after_read": after_read,
        "routes": [
            {
                "path":"login", 
                "methods":["POST"], 
                "function":api_login,
            },
            {
                "path":"logout", 
                "methods":["POST"], 
                "function":api_logout,
            },
            {
                "path": "pwreset",
                "methods": ["GET"],
                "keyed_url": True,
                "function": api_get_password_reset_key
            },
            {
                "path": "pwreset",
                "methods": ["POST"],
                "function": api_password_reset
            },
        ],
    }

    # meta data and type that are exposed via read/write with type and defaults
    META = {
        "username":{
            "key": True,
            "type": str,
            "regex": "^(?i)[a-z0-9\_.:]{1,128}$",
            "default": ""
        },
        "password": {
            "type": str,
            "regex": "^.{1,256}$",
            "hash": True,
            "read": False,
            "default": "password"
        },
        "role": {
            "type": int,
            "default": Role.USER,
            "min": Role.MIN_ROLE,
            "max": Role.MAX_ROLE,
        },
        "last_login": {
            "type": float,
            "write": False,
        },
        "password_reset_key": {
            "type": str,
            "read": False,
            "write": False,
        },
        "password_reset_timestamp": {
            "type": float,
            "read": False,
            "write": False,
        },
    }
   
    # required for flask-login
    # https://flask-login.readthedocs.org/en/latest/#your-user-class
    def is_authenticated(self): return True
    def is_active(self): return True
    def is_anonymous(self): return False
    def get_id(self): return self.username

    @staticmethod
    def login(username, password, force=False):
        """ authenticate username and password. On success create user session
            return boolean authentication success
            set force to True to skip password validate and allow login
        
            on success last_login timestamp is updated. If the user did not
            previousy exists, the save() operation will create the user
        """
        success = False
        if username is None: return False
        u = User.load(username=username)
        if force: success = True
        else:
            from flask_bcrypt import check_password_hash
            try:
                if check_password_hash(u.password, password): success = True
            except Exception as e:
                User.logger.error("User failed to check hash: %s" % e)

        # on successfully login, start user session
        if success:
            u.last_login = time.time()
            u.save()
            login_user(u, remember=True)
        return success

    @staticmethod
    def get_password_reset_key(username):
        """ generates a password reset key, inserts into database for user,
            and returns key.  
        """
        u = User.load(username=username)
        if not u.exists():
            abort(404, "User(%s) not found" % username)

        # non-admins can only get a pwreset link for thier account
        if g.user.role != Role.FULL_ADMIN and username != g.user.username:
            abort(403, MSG_403)

        # create a temporary random key and timestamp it
        u.password_reset_key = "%s"%uuid.uuid4()
        u.password_reset_timestamp = time.time()
        u.save()
        return u.password_reset_key

    @staticmethod
    def password_reset(username, password, password_reset_key):
        """ a non-authenticated user provides correct username and pw_reset_key
            within the pw_reset_timestamp. If successful, then provided 
            password will be updated for user.
            aborts on failure
        """
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



