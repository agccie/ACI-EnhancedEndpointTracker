
from flask import jsonify, request, abort, g, current_app
from utils import (get_user_data, MSG_403, convert_to_list, 
        force_attribute_type, filtered_read)
from pymongo.errors import DuplicateKeyError
import time, json, logging

from .users import Users
from .rest import Rest

class Groups(Rest):
    """ Groups REST class """

    # module level logger
    logger = logging.getLogger(__name__)

    # meta data and type that are exposed via read/write with type and defaults
    META = {
        "group": {"type": str, "default": "", "read":True, "write": False},
        "members": {"type": list, "default":[], "read":True, "write":True, 
                    "subtype": str},
    }

    def __init__(self):
        super(Rest, self).__init__()

    @classmethod
    def create(cls):
        """ api call - create new group, returns dict with group name  """
       
        # special checks for group put in override fields 
        data = get_user_data(["group"])
        group = force_attribute_type("group", str, data["group"])
        if group == "incr":
            abort(400, "'incr' is no a valid group name")

        # create new group 
        Rest.create.__func__(cls, current_app.mongo.db.groups,
            rule_dn = "/groups/",
            required_attr = [],
            override_attr = {"group": group}
        )

        # add group to list of users if 'members' provided
        if "members" in data and len(data["members"])>0:
            Users.add_groups(data["members"], group)

        # create returns dict, not json, allowing calling function to
        # add/remove attributes as required by api
        return {"success": True, "group":group} 
 
    @classmethod
    def read(cls, group=None):
        """ api call - read one or more groups """
  
        if group is not None: read_one = ("group", group)
        else: read_one = None
        
        return Rest.read.__func__(cls, current_app.mongo.db.groups,
            rule_dn = "/groups/",
            filter_rule_base = "/groups/",
            filter_rule_key = "group",
            read_one = read_one
        )

    @classmethod
    def update(cls, group):
        """ api call - update a single group (full set update...) """

        # if 'members' in update, then we're overwriting field. This means
        # we need to read the current members BEFORE performing the update
        data = get_user_data([])
        members = []
        members_update = False
        if "members" in data:
            members_update = True
            r = current_app.mongo.db.groups.find_one({"group":group})
            if r is not None and "members" in r and len(r["members"])>0 and \
                type(r["members"]) is list:
                # append to members members from current group
                members+= r["members"]

        # perform update (aborts on error)
        update = Rest.update.__func__(cls, current_app.mongo.db.groups,
            update_one = ("group", group),
            rule_dn = "/groups/%s" % group,
        )
        
        if members_update:
            # remove group from old members (full list of old members)
            if len(members)>0:
                Users.remove_groups(members, group)
            # add group to new members
            if "members" in update and len(update["members"])>0:
                Users.add_groups(update["members"], group)

        return {"success": True}

    @classmethod
    def update_incr(cls):
        """ api call - incremental add/remove of entries in list
            - group is provided as a required attribute (similar to create)
            - list_name {"add":[list], "remove":[list]}
        """

        # get user data with required parameters (only dn is required)
        data = get_user_data(["group"])
        group = force_attribute_type("group", Groups.META["group"]["type"], 
            data["group"])

        # perform update_incr (aborts on error)
        update = Rest.update_incr.__func__(cls, current_app.mongo.db.groups,
            update_one = ("group", group),
            rule_dn = "/groups/%s" % group,
        )

        # need to remove/add users from appropriate groups
        # (always perform 'remove' operation first)
        if "members" in update:
            m_update = update["members"]
            if "remove" in m_update and len(m_update["remove"])>0:
                Users.remove_groups(m_update["remove"], group)
            if "add" in m_update and len(m_update["add"])>0:
                Users.add_groups(m_update["add"], group)
                
        return {"success": True}

    @classmethod
    def delete(cls, group):
        """ api call - delete group """

        # need to read members before deleting group
        members = []
        r = current_app.mongo.db.groups.find_one({"group":group})
        if r is not None and "members" in r and len(r["members"])>0: 
            members = r["members"]

        # perform delete operation
        Rest.delete.__func__(cls, current_app.mongo.db.groups,
            delete_one = ("group", group),
            rule_dn = "/groups/%s" % group
        )

        # remove group from all previous members
        if len(members)>0: Users.remove_groups(members, group)

        return {"success": True}
