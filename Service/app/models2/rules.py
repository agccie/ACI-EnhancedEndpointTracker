
from flask import request, abort, g, current_app
from utils import (get_user_data, MSG_403, convert_to_list,
        force_attribute_type, filtered_read)
from pymongo.errors import DuplicateKeyError
import logging

from .roles import Roles
from .rest import Rest

class Rules(Rest):
    """ Rules REST object """

    # module level logger
    logger = logging.getLogger(__name__)

    # meta data and type that are exposed via read/write with type and defaults
    META = {
        "dn": {"type": str, "default": "", "read":True, "write": False},
        "inherit_read":{"type": bool, "default":True,"read":True,"write":True},
        "inherit_write":{"type": bool, "default":True,"read":True,"write":True},
        "owner": {"type": str, "default":"", "read":True, "write": False},
        "read_users": {"type": list, "default":[], "read":True, "write":True},
        "read_groups": {"type": list, "default":[], "read":True, "write":True},
        "write_users": {"type": list, "default":[], "read":True, "write":True},
        "write_groups": {"type": list, "default":[], "read":True, "write":True},
    }
    
    def __init__(self, d):
        """ create new rule from provided dict """
        self.dn = kwargs.get("dn", None)
        self.owner = kwargs.get("owner", None)
        self.inherit = kwargs.get("inherit", Rules.META["inherit"]["default"])
        self.read_users = kwargs.get("read_users", 
            Rules.META["read_users"]["default"])
        self.write_users = kwargs.get("write_users", 
            Rules.META["write_users"]["default"])
        self.read_groups = kwargs.get("read_groups", 
            Rules.META["read_groups"]["default"])
        self.write_groups = kwargs.get("write_groups", 
            Rules.META["write_groups"]["default"])

        assert self.dn is not None, "dn must be provided"
        assert self.owner is not None, "owner is required"

    @staticmethod
    def create():
        """ api call - create new rule, returns DICT (not json)  """

        # get user data with required parameters (only dn is required)
        data = get_user_data(["dn"])
       
        # minimum required attributes 
        update = {"dn": data["dn"]}

        # for now only admins can set owner - might open up later...
        if g.user.role == Roles.FULL_ADMIN and "owner" in data:
            update["owner"] = data["owner"]            
        else:
            update["owner"] = g.user.username

        # validate mandatory attributes
        for v in ("dn", "owner"):
            update[v] = force_attribute_type(v, str, update[v])

        # dn must always be in the form /path...
        update["dn"] = "/%s" % update["dn"].strip("/")

        # reserved dn 'incr' used by api call to update_incr
        if update["dn"] == "/incr":
            abort(400, "'/incr' is no a valid DN")

        # validate optional attributes
        for v in Rules.META:
            if Rules.META[v]["write"] and v in data and v not in update:
                update[v] = force_attribute_type(v, Rules.META[v]["type"], 
                    data[v])
            elif v not in update:
                # ensure all attributes are set for create operation
                update[v] = Rules.META[v]["default"]

        # if attribute provided that cannot be written, return error
        for v in data:
            # skip 'dn' and 'owner', already handled
            if v == "dn" or v == "owner": continue
            if v not in Rules.META or not Rules.META[v]["write"]:
                abort(400, "unknown or invalid attribute '%s'" % v)
            
        try:
            current_app.mongo.db.rules.insert_one(update)
        except DuplicateKeyError as e:
            abort(400, "Dn \"%s\" already exists" % update["dn"])

        # create returns dict, not json, allowing calling function to
        # add/remove attributes as required by api
        return {"success": True, "dn": update["dn"]}

    @staticmethod
    def read(dn=None):
        """ api call - read one or more rules """
    
        flt = {}
        if dn is not None:
            dn = force_attribute_type("dn", Rules.META["dn"]["type"], dn)
            flt["dn"] = dn

        # read rules
        results = filtered_read(current_app.mongo.db.rules, 
            meta=Rules.META, filters=flt)

        # dn only provided on read_rule, need 404 error if not found
        if dn is not None:
            if len(results) == 0: abort(404, "DN(%s) not found" % dn)
            return results[0]

        # return full list of rules
        return {"rules":results}

    @staticmethod
    def update(dn):
        """ api call - update a single rule (full set update...) """

        dn = force_attribute_type("dn", Rules.META["dn"]["type"], dn)
        # build update list based on user data and writeable attributes
        data = get_user_data([])
        update = {}
        for attr in Rules.META:
            if Rules.META[attr]["write"] and attr in data:
                update[attr] = force_attribute_type(attr, 
                    Rules.META[attr]["type"], data[attr])

        # for now only admins can set owner - might open up later...
        if g.user.role == Roles.FULL_ADMIN and "owner" in data:
            update["owner"] = data["owner"]            

        # if attribute provided that cannot be written, return error
        for v in data:
            # skip 'dn' and 'owner' (already handled)
            if v == "dn" or v == "owner": continue
            if v not in Rules.META or not Rules.META[v]["write"]:
                abort(400, "unknown or invalid attribute '%s'" % v)

        # ensure at least one valid attribute provided for rule
        if len(update)==0: abort(400, "no valid parameter provided")
        r = current_app.mongo.db.rules.update_one({"dn":dn}, {
            "$set": update
        })
        if r.matched_count == 0: abort(404, "Rule(%s) not found" % dn)
        return {"success": True}


    @staticmethod
    def update_incr():
        """ api call - incremental add/remove of entries in list
            - dn is provided as a required attribute (similar to create)
            - list_name {"add":[list], "remove":[list]}
        """

        # get user data with required parameters (only dn is required)
        data = get_user_data(["dn"])
        dn = force_attribute_type("dn", Rules.META["dn"]["type"], data["dn"])
        update = {}

        # validate optional attributes
        for v in ("read_users", "write_users", "read_groups", "write_groups"):
            if v in data:
                update[v] = {}
                if type(data[v]) is not dict:
                    abort(400, "attribute '%s' should by type 'dict'" % v)
                for opt in ("add", "remove"):
                    if opt not in data[v]: continue
                    if type(data[v][opt]) is not list:
                        abort(400, "attribute %s[%s] should be type 'list'" % (
                            v, opt))
                    if len(data[v][opt]) == 0: continue
                    update[v][opt] = []
                    for entry in data[v][opt]:
                        # force entry to string and append to update
                        update[v][opt].append(str(entry))
                # no validate data provided, pop index
                if len(update[v]) == 0: update.pop(v, None)
                  

        # ensure at least one valid attribute provided for rule
        if len(update)==0: 
            incr_msg = "Expected at least one 'add' or 'remove' attribute"
            abort(400, "No valid parameter provided. %s" % incr_msg)

        # perform add/remove updates
        for v in update:
            if "add" in update[v] and len(update[v]["add"])>0:
                r = current_app.mongo.db.rules.update_one({"dn":dn}, {
                    "$addToSet": {v: {"$each": update[v]["add"]}}
                })               
                if r.matched_count == 0: abort(404, "Rule(%s) not found" % dn)
            if "remove" in update[v] and len(update[v]["remove"])>0:
                r = current_app.mongo.db.rules.update_one({"dn":dn}, {
                    "$pullAll": {v: update[v]["remove"]}
                })               
                if r.matched_count == 0: abort(404, "Rule(%s) not found" % dn)
                
        return {"success": True}
        

    @staticmethod
    def delete(dn):
        """ api call - delete dn """

        dn = force_attribute_type("dn", Rules.META["dn"]["type"], dn)
        r = filtered_read(current_app.mongo.db.rules, 
            meta=Rules.META, filters={"dn":dn})
        if len(r)==0: abort(404, "Rule(%s) not found" % dn)

        # for now, only admin or rule owner can delete rule
        if g.user.role != Roles.FULL_ADMIN and \
            r[0]["owner"] != g.user.username:
                abort(403, MSG_403)

        # delete the rule
        r = current_app.mongo.db.rules.delete_one({"dn":dn})
        # verify delete occurred
        if r.deleted_count == 0: abort(404, "DN(%s) not found" % dn)
        return {"success": True}
