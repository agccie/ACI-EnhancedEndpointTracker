
from flask import jsonify, request, abort, g, current_app
from flask_login import (login_user, logout_user)
from utils import (get_user_data, random_str, MSG_403, force_attribute_type,
    filtered_read, convert_to_list)
from pymongo.errors import DuplicateKeyError
import time, json, logging

from .roles import Roles
from .rest import Rest

class Users(Rest):

    # module level logger
    logger = logging.getLogger(__name__)

    # meta data and type that are exposed via read/write with type and defaults
    META = {
        "username":     {"type": str,"default":"","read":True,"write":False},
        "password":     {"type": str,"default":"","read":False,"write":True},
        "role":         {"type": int, "default": Roles.USER, 
                            "read":True, "write":True},
        "last_login":   {"type":float, "default": 0.0, 
                            "read":True,"write":False},
        "groups":       {"type":list, "default":[], "read":True,"write":False},
    }
   
    def __init__(self, d):
        """ create new user from provided dict """
        self.username = d.get("username", None)
        self.role = d.get("role", Users.META["role"]["default"])
        self.password = d.get("password", Users.META["password"]["default"])
        self.pw_reset_key = d.get("pw_reset_key", "")
        self.pw_reset_timestamp = d.get("pw_reset_timestamp", 0)
        self.last_login = d.get("last_login", None)
        self.groups = d.get("groups", [])
        assert self.username is not None, "username must be provided"

        super(Rest, self).__init__()

    # required for flask-login
    # https://flask-login.readthedocs.org/en/latest/#your-user-class
    def is_authenticated(self): return True
    def is_active(self): return True
    def is_anonymous(self): return False
    def get_id(self): return self.username

    def _auto_create(self):
        """ add a new user to database based on valid authentication """

        self.logger.debug("auto-create for user:%s,role:%s" % (
            self.username,self.role))
        if not Roles.valid(self.role):
            self.logger.warning("Invalid value for role '%s'" % self.role)
            self.role = Roles.get_default()
        try:
            # find groups that user may already be a member of
            groups = Users.find_groups(self.username)

            current_app.mongo.db.users.insert_one({
                "username": self.username,
                "password": Users.hash_pass(self.password),
                "role": self.role,
                "groups": groups
            })
        except DuplicateKeyError as e:
            self.logger.warning("User \"%s\" already exists"%self.username)
        return None

    @classmethod
    def create(cls):
        """ api call - create new user, returns dict with username  """

        # get user data with required parameters and validate parameters
        data = get_user_data(["username", "password"])
        username = force_attribute_type("username", 
            Users.META["username"]["type"], data["username"])
        password = Users.hash_pass(force_attribute_type("password",
            Users.META["password"]["type"], data["password"]))
        role = data.get("role", Users.META["role"]["default"])
        if not Roles.valid(role): abort(400, "Invalid role: %s" % role)

        # block 'root' user from being created
        if username=="root": abort(400, "invalid username \"%s\"" % username)

        # find groups that user may already be a member of
        groups = Users.find_groups(username)

        # create user
        update = Rest.create.__func__(cls, current_app.mongo.db.users,
            rule_dn = "/users/",
            override_attr = {
                "username": username,
                "password": password,
                "role": role,
                "groups": groups
            }
        )
        return {"success": True, "username": username}

    @classmethod
    def read(cls, username=None):
        """ api call - read one or more groups """

        if username is not None: read_one = ("username", username)
        else: read_one = None

        return Rest.read.__func__(cls, current_app.mongo.db.users,
            rule_dn = "/users/",
            filter_rule_base = "/users/",
            filter_rule_key = "username",
            read_one = read_one
        )

    @classmethod
    def update(cls, username):
        """ api call - update user """

        # pre-processing custom attributes
        data = get_user_data([])
        override_attr = {} 
        
        # encrypt password if provided in update
        if "password" in data:
            override_attr["password"] = User.hash_pass(force_attribute_type(
                "password",cls.META["password"]["type"], data["password"]))
        # validate role if provided in update
        if "role" in data:
            if not Roles.valid(data["role"]): 
                abort(400, "Invalid role: %s" % data["role"])
            override_attr["role"] = data["role"]
        
        # perform update (aborts on error)
        update = Rest.update.__func__(cls, current_app.mongo.db.users,
            update_one = ("username", username),
            rule_dn = "/users/%s" % username,
            override_attr = override_attr,
        )
        return {"success": True}

    @classmethod
    def delete(cls, username):
        """ api call - delete user """

        # do not allow user to delete reserved values
        data = get_user_data([], relaxed=True)
        if username in (g.user.username, "admin", "root"):
            abort(400, "You cannot delete this account")

        # need to get groups before deleting user so they can be cleaned up
        groups = []
        r = current_app.mongo.db.users.find_one({"username":username})
        if r is not None and "groups" in r and len(r["groups"])>0: 
            groups = r["groups"]

        # perform delete operation
        Rest.delete.__func__(cls, current_app.mongo.db.users,
            delete_one = ("username", username),
            rule_dn = "/users/%s" % username
        )

        # remove user from groups
        if "sync_groups" in data and data["sync_groups"]:
            r = current_app.mongo.db.groups.update_many({},{
                "$pull":{"members":"%s" % username}}) 
            cls.logger.debug("removed user:%s from %s groups" % (
                username, r.modified_count)) 
        return {"success": True}

    @staticmethod
    def load_user(username):
        """ search database for username and return object if found """
        r = current_app.mongo.db.users.find({"username":username})
        if r.count() > 0: return Users(r[0])
        return None

    @staticmethod
    def hash_pass(password):
        """ Return the bcrypt hash of the password """
        # lazy import for rare function call
        from flask.ext.bcrypt import generate_password_hash
        return generate_password_hash(password, 
            current_app.config["BCRYPT_LOG_ROUNDS"])

    @staticmethod
    def login(**kwargs):
        """
        authenticate user email/password and on success create user session.
        Returns simple boolean variable.
        """
        username = kwargs.get("username", None)
        password = kwargs.get("password", None)
        remember = kwargs.get("remember", True)
        success = False
        u = Users.load_user(username)
        if u is not None:
            from flask.ext.bcrypt import check_password_hash
            if check_password_hash(u.password, password):
                Users.start_session(username)
                success = True
        return success

    @staticmethod
    def start_session(username, **kwargs):
        """
        after user is successfully authenticated, start user session
        if user is not in local database, add them
        """
        remember = kwargs.get("remember", True)
        u = Users.load_user(username)
        # if user does not exist, create it with random local password
        if u is None:
            u = Users({"username":username, "password":random_str()})
            u._auto_create()
        login_user(u, remember=remember)
        current_app.mongo.db.users.update_one({"username":u.username},{
            "$set": {"last_login": time.time()}
        })

    @staticmethod
    def logout():
        """ logout user """
        logout_user()

    @staticmethod
    def get_pwreset_key(username):
        # 'routing' handles the authentication, user should be authenticated
        # in order to request a pwreset link (usually admin)
        # this may change if we get email functionality.  Note, this function
        # may not be aware of routing so will not be used to generate link.  
        # Instead, only pwreset key is returned on success.
        u = Users.load_user(username)
        if u is None:
            abort(404, "User(%s) not found" % username)

        # non-admins can only get a pwreset link for thier account
        if g.user.role != Roles.FULL_ADMIN and username != g.user.username:
            abort(403, MSG_403)

        # create a temporary random key and timestamp it
        key = random_str()
        current_app.mongo.db.users.update_one({"username":u.username},{
            "$set":{"pw_reset_key": key, "pw_reset_timestamp": time.time()}
        })
        return key

    @staticmethod
    def update_pwreset():
        # only allowed non-authenticated update.  User must provide correct
        # username and key within pwreset timeout for successful reset

        # get user data with required parameters
        data = get_user_data(["username", "password", "key"])
        u = Users.load_user(data["username"])
        if u is None:
            abort(400, "Incorrect username or inactive key provided")

        # ensure key is correct and still valid
        if data["key"] != u.pw_reset_key:
            abort(400, "Incorrect username or inactive key provided")

        pwtimeout = int(current_app.config.get("pw_reset_timeout", 7200))
        if u.pw_reset_timestamp+pwtimeout < int(time.time()):
            # key has timed out, reset it and return an error
            current_app.mongo.db.users.update_one({"username":u.username},{
                "$set": { "pw_reset_key": "", "pw_reset_timestamp": 0},
            })

            #abort(400, "key timeout (now: %s/saved: %s/diff: %s)" %(
            #    int(time.time()),
            #    u.pw_reset_timestamp,
            #    int(time.time()) - (u.pw_reset_timestamp+pwtimeout)
            #))
            abort(400, "Incorrect username or inactive key provided")

        # ok to update password
        current_app.mongo.db.users.update_one({"username":u.username},{
            "$set": { "pw_reset_key": "", "pw_reset_timestamp": 0,
                "password": Users.hash_pass(data["password"])},
        })
        return {"success": True}

    @staticmethod
    def find_groups(users):
        """ search group collection and return all groups in which provider
            users are a member.
            return list of groups
        """
        users = convert_to_list(users)
        groups = []
        for r in current_app.mongo.db.groups.find({
            "members":{"$in":users}}):
            if "group" in r: groups.append("%s" % r["group"])
        return groups

    @staticmethod
    def add_groups(users, group): return Users.sync_groups(users, group, True)

    @staticmethod
    def remove_groups(users, group): return Users.sync_groups(users,group,False)

    @staticmethod
    def sync_groups(users, groups, add=True):
        """ add/remove list of groups to the group attribute of provide users.
            Note, this is not triggered from api call, must manually be called
            (intention from Groups updates)
            return number of users updated
        """
        users = convert_to_list(users)
        groups = convert_to_list(groups)
        if len(users) <= 0: return 0
        if len(groups) <= 0: return 0
        
        if add:
            # add groups to users
            # (note, addToSet only adds if not already present
            r = current_app.mongo.db.users.update_many({
                "username": {"$in": users}
            },{
                "$addToSet": {"groups": {"$each": groups}}
            })
            return r.matched_count
        else:
            # remove groups from users
            r = current_app.mongo.db.users.update_many({
                "username": {"$in": users}
            },{
                "$pullAll": {"groups": groups}
            })               
            return r.matched_count
