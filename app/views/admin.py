
from flask import current_app, Blueprint, render_template
admin = Blueprint("admin", __name__)

from flask import Flask, jsonify, redirect, url_for
from flask import request, make_response, g, abort
from flask_login import (login_required, current_user)

from ..models.users import Users
from ..models.settings import Settings
from ..models.rules import Rules
from ..models.roles import Roles
from ..models.groups import Groups

@admin.route("/users")
@admin.route("/users/")
@login_required
def users():
    # ensure user is full admin
    if g.user.role != Roles.FULL_ADMIN: abort(403)
    return render_template("admin/users.html")

@admin.route("/settings")
@admin.route("/settings/")
@login_required
def settings():
    # ensure user is full admin
    if g.user.role != Roles.FULL_ADMIN: abort(403)
    return render_template("admin/settings.html")

##############################################################################
# admin function API, imported by api module
##############################################################################

##### CREATE #####

def create_user():
    """ create a new user
        Args:
            username(str): new user's username
            password(str): new user's password
            role(int): new user's Role

        Returns:
            location(str): resource location of new user
            successs(bool): successfully created user
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    if g.user.role != Roles.FULL_ADMIN: abort(403)

    # lazy import for creating location attribute for new resource
    from .api import admin_read_user
    result = Users.create()
    if "success" in result and result["success"] and "username" in result:
        result["location"] = url_for("api.admin_read_user",
            username=result["username"].lstrip("/"))
    return jsonify(result)


def create_rule():
    """ create a new rule
        Args:
            dn(str): distinguished name for rule
            owner(str): rule owner (defaults to current user)
            inherit(bool): sub-dn's inherit this rule if not specific rule 
                           specified
            read_users(list): list of usernames with read access
            read_groups(list): list of groups with read access
            write_users(list): list of usernames with write access
            write_groups(list): list of groups with write access

        Returns:
            location(str): resource location of new rule
            successs(bool): successfully created rule
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    
    # lazy import for creating location attribute for new resource
    from .api import admin_read_rule
    result = Rules.create()
    if "success" in result and result["success"] and "dn" in result:
        result["location"] = url_for("api.admin_read_rule",
            dn=result["dn"].lstrip("/"))
    return jsonify(result)

def create_group():
    """ create a new group
        Args:
            group(str): group name
            owner(str): group owner (defaults to current user)
            members(list): list of members in the group

        Returns:
            location(str): resource location of new group
            successs(bool): successfully created group
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    
    # lazy import for creating location attribute for new resource
    from .api import admin_read_group
    result = Groups.create()
    if "success" in result and result["success"] and "group" in result:
        result["location"] = url_for("api.admin_read_group",
            group=result["group"].lstrip("/"))
    return jsonify(result)


##### READ #####

def read_config():
    """ get site configuration

        Returns:
            app_name(str): name of the application
            force_https(bool): redirect all application requests to https
            fqdn(str): application fully qualified domain name
            pw_reset_timeout(int): timeout in seconds for password reset link
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Settings.read())

def read_users():
    """ read all users

        Returns:
            users(list): list of user objects
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Users.read())

def read_user(username):
    """ read a single user

        Returns:
            username(str): username
            role(int): user role
            last_login(float): unix timestamp of last login
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Users.read(username))

def read_user_pwreset(username):
    """ get a temporary password reset link for user. The reset link can only
        be requested by users with admin privilege or for current_user's
        username

        Returns:
            url(str): password reset link with embedded reset key
            key(str): password reset key
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    key = Users.get_pwreset_key(username)
    url = url_for("auth.pwreset", key=key).lstrip("/")
    return jsonify({
        "url": "%s%s" % (request.url_root, url),
        "key": "%s" % key
    })

def read_rules():
    """ read all rules

        Returns:
            rules(list): list of rule objects
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Rules.read())

def read_rule(dn):
    """ read a single rule

        Returns:
            dn(str): distinguished name for rule
            owner(str): rule owner
            inherit(bool): sub-dn's inherit this rule if not specific rule 
                           specified
            read_users(list): list of usernames with read access
            read_groups(list): list of groups with read access
            write_users(list): list of usernames with write access
            write_groups(list): list of groups with write access
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Rules.read(dn))

def read_groups():
    """ read all groups

        Returns:
            groups(list): list of group objects
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Groups.read())

def read_group(group):
    """ read a single group

        Returns:
            group(str): group name
            owner(str): group owner
            members(list): list of group members
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Groups.read(group))

##### UPDATE #####

def update_config():
    """ update one or more attributes of application config/settings.

        Args:
            app_name(str): name of the application
            force_https(bool): redirect all application requests to https
            fqdn(str): application fully qualified domain name
            pw_reset_timeout(int): timeout in seconds for password reset link

        Returns:
            success(bool): successfully updated
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Settings.update())

def update_user(username):
    """ Update attributes for a single user. Only users with 'role' admin
        can update users.

        Args:
            password(str): user's password
            role(int): user's role

        Returns:
            success(bool): successfully updated
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    if g.user.role != Roles.FULL_ADMIN: abort(403)
    return jsonify(Users.update(username))

def update_user_pwreset():
    """ reset user password

        Args:
            username(str): username
            password(str): new password for user
            key(str): password reset key for user

        Returns:
            success(bool): successfully updated
    """
    # only allowed non-authenticated request
    return jsonify(Users.update_pwreset())

def update_rule(dn):
    """ Update attributes for a single rule.  Note, for list attributes,
        the full list is updated with the provided value.  For incremental 
        add/removal from a list, use the /incr function

        Args:
            owner(str): rule owner 
            inherit(bool): sub-dn's inherit this rule if not specific rule 
                           specified
            read_user(list): list of usernames with read access
            read_group(list): list of groups with read access
            write_user(list): list of usernames with write access
            write_group(list): list of groups with write access

        Returns:
            success(bool): successfully updated
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Rules.update(dn))

def update_rule_incr():
    """ Incrementally add/remove entries in a single rule's access lists.
        Example post:

        {
            "dn": "/path/for/dn",
            "read_users": {
                "add": ["user1", "user2"],
                "remove": ["user3"]
            }
        }

        Args:
            dn(str): dn of rule to update
            read_user(dict): 'add' and 'remove' lists of entries
            read_group(dict): 'add' and 'remove' lists of entries
            write_user(dict): 'add' and 'remove' lists of entries
            write_group(dict): 'add' and 'remove' lists of entries

        Returns:
            success(bool): successfully updated
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Rules.update_incr())

def update_group(group):
    """ Update attributes for a single group.  Note, for list attributes,
        the full list is updated with the provided value.  For incremental 
        add/removal from a list, use the /incr function

        Args:
            members(list): list of group members

        Returns:
            success(bool): successfully updated
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Groups.update(group))

def update_group_incr():
    """ Incrementally add/remove entries in a single group's access lists.
        Example post:

        {
            "group": "group1",
            "members": {
                "add": ["user1", "user2"],
                "remove": ["user3"]
            }
        }

        Args:
            group(str): group to be updated
            members(dict): 'add' and 'remove' lists of entries

        Returns:
            success(bool): successfully updated
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Groups.update_incr())

##### DELETE #####

def delete_user(username):
    """ delete user

        Args:
            sync_groups(bool):  remove user from any groups. By default
                                all group membership is maintained.

        Returns:
            success(bool): user successfully deleted
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    if g.user.role != Roles.FULL_ADMIN: abort(403)
    return jsonify(Users.delete(username))

def delete_rule(dn):
    """ delete rule
    
        Returns:
            success(bool): rule successfully deleted
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Rules.delete(dn))

def delete_group(group):
    """ delete group
    
        Returns:
            success(bool): group successfully deleted
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(Groups.delete(group))
