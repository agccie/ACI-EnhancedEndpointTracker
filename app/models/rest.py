
from flask import request, abort, g, current_app
from utils import (get_user_data, MSG_403, convert_to_list, combine_list,
        force_attribute_type, filtered_read)
from pymongo.errors import DuplicateKeyError
import logging

from .roles import Roles

class Rest(object):
    """ generic REST object providing common rest functionality.  All other 
        REST model objects should inherit this class and overwrite 
        functionality as needed
    """
    logger = logging.getLogger(__name__)
 
    # dict of meta data indexed by attribute name. Each attribute is a dict
    # that must have the following 
    #   'type': type object (generally limited to str, int, list, or dict)
    #   'default': default value for attribute
    #   'read': boolean, whether API calls can read this value
    #   'write': boolean, whether API calls can update this value
    #   
    # ex (read-only attribute): {
    #   "attr1":{"type":str,"default":"","read":True,"write":False}
    # }
    META = {}

    # unique key used for collection, defaults to _id
    UNIQUE_KEY = "_id"

    def __init__(self, d=None):
        """ create a new instance of object based on provided dict """
        pass

    @classmethod
    def create(cls, collection, **kwargs):
        """ api call - create new rest object, aborts on error.
            
            Parameters
                collection      - mongo database collection object (required)
                su              - super user (boolean) has read/write access    
                                  to all attributes. Defaults to False
                rule_dn         - list of rule dns to enforce r/w privilege
                                  if list then rule_match_all attribute to 
                                  decide whether user must match one/all rules
                rule_match_all  - boolean.  Defaults to True
                required_attr   - list of required attributes 
                override_attr   - dict of attribute values that overwrite
                                  any user provided fields.  dict key is 
                                  attribute and value is the override value.
               
                * note, attributes in required_attr/override_attr are excluded
                  in invalid attribute validation.  This allows create to
                  specify attributes that might have a False write attribute in
                  meta data.

            Return
                obj          - dict object inserted into database
        """
        su = kwargs.get("su", False)
        rule_dn = convert_to_list(kwargs.get("rule_dn", None))
        rule_match_all = kwargs.get("rule_match_all", True)
        required_attr = kwargs.get("required_attr", [])
        override_attr = kwargs.get("override_attr", {})

        cls.logger.debug("create %s user:%s,su:%s,rule:%s,match-all:%r" % (
            cls.__name__, g.user.username, su, rule_dn, rule_match_all))

        # validate user has permission to write to this path.  
        check_user_access(su=su, rules=rule_dn, match_all=rule_match_all, 
            write_required=True, cls=cls)

        # get user data with required parameters 
        data = get_user_data(required_attr)

        # minimum required attributes 
        update = {}
        for a in required_attr: 
            update[a] = force_attribute_type(a, cls.META[a]["type"], data[a],
                control=cls.META[a])

        # override values (no force_attribute_type check for override)
        for a in override_attr: update[a] = override_attr[a]

        # super user access - do not validate write attributes
        if su:
            # add existing attributes to list, return error for invalid attr
            for a in cls.META:
                if a in data and a not in update:
                    update[a] = force_attribute_type(a, cls.META[a]["type"], 
                        data[a], control=cls.META[a])

                elif a not in update:
                    update[a] = cls.META[a]["default"]
            # if attribute provided that cannot be written, return error
            for a in data:
                if a in required_attr or a in override_attr: continue 
                if a not in cls.META:
                    dm = "failed to create '%s', " % cls.__name__
                    dm+= "unknown or invalid attribute '%s'" % a
                    cls.logger.debug(dm)
                    abort(400, dm)

        # all other users same check with write attributes
        else:
            # validate optional attributes
            for a in cls.META:
                if cls.META[a]["write"] and a in data and a not in update:
                    update[a] = force_attribute_type(a, cls.META[a]["type"], 
                        data[a], control=cls.META[a])
                elif a not in update:
                    # ensure all attributes are set for create operation
                    update[a] = cls.META[a]["default"]

            # if attribute provided that cannot be written, return error
            for a in data:
                # skipping required_attr and override_attr
                if a in required_attr or a in override_attr: continue 
                if a not in cls.META or not cls.META[a]["write"]:
                    dm = "failed to create '%s', " % cls.__name__
                    dm+= "unknown or invalid attribute '%s'" % a
                    cls.logger.debug(dm)
                    abort(400, dm)
            
        # insert the update into the collection
        try:
            collection.insert_one(update)
        except DuplicateKeyError as e:
            cls.logger.debug("duplicate entry cls: %s, e: %s" % (
                cls.__name__,e))
            abort(400, "duplicate entry for \"%s\"" % cls.__name__)

        # return object inserted into database
        return update
        
    @classmethod
    def read(cls, collection, **kwargs):
        """ api call to read one or more entries from collection
            aborts on error, else returns dict reply
            
            Parameters
                collection      - mongo database collection object (required)
                su              - super user (boolean) has read/write access
                                  to all attributes. Defaults to False
                rule_dn         - list of rule dns to enforce r/w privilege
                                  if list then rule_match_all attribute to 
                                  decide whether user must match one/all rules
                rule_match_all  - boolean.  Defaults to TrueS
                filter_attr     - dict of attribute values to filter query
                filter_rule_key - 
                filter_rule_base- to filter results based on read/write priv
                                  a rule_base combined with a rule_key are used 
                                  to create rule_dn's that will filter read
                                  results.
                projection      - mongodb projection list to filter returned
                                  attributes
                sort            - string attribute to sort results
                sort_descend    - boolean, use descend sort (else use ascend)
                limit           - integer limit for number of results returned 
                read_one        - tuple in form (key, value) that is used to
                                  read a single value from collection. Presence
                                  of this argument means that only a single 
                                  value will be returned (and 404 returned if 
                                  not found).  Else, a list of results returned
                                  in form {"classname".lower(): [(values)]}

            Returns
                obj             - dict result of read
        """
    
        su = kwargs.get("su", False)
        rule_dn = convert_to_list(kwargs.get("rule_dn", None))
        rule_match_all = kwargs.get("rule_match_all", True)
        filter_attr = kwargs.get("filter_attr", {})
        filter_rule_key = kwargs.get("filter_rule_key", None)
        filter_rule_base = kwargs.get("filter_rule_base", None)
        sort = kwargs.get("sort", None)
        sort_descend = kwargs.get("sort_descend", False)
        limit = kwargs.get("limit", None)
        projection = kwargs.get("projection", None)
        read_one = kwargs.get("read_one", None)

        #cls.logger.debug("read %s user:%s,su:%s,rule:%s,match-all:%r" % (
        #    cls.__name__, g.user.username, su, rule_dn, rule_match_all))

        if read_one is not None:
            if not isinstance(read_one, tuple) or len(read_one)!=2:
                cls.logger.debug("invalid value for read_one arg: %s"%read_one)
            filter_attr[read_one[0]] = read_one[1]

        # validate user has permission to read from this path.  
        check_user_access(su=su, rules=rule_dn, match_all=rule_match_all, 
            read_required=True, cls=cls)

        # perform read
        results = filtered_read(collection, meta=cls.META, 
            filters=filter_attr, su=su, projection=projection, sort=sort,
            sort_descend=sort_descend, limit=limit)

        # filter results based on filter_rule_base + filter_rule_key
        if not su and filter_rule_base is not None and \
            filter_rule_key is not None:
            base = "/%s" % filter_rule_base.strip("/")
            dn = []
            # build dns for rules first so execute_rule is only called once
            for r in results:
                if filter_rule_key in r: 
                    dn.append("%s/%s" % (base, r[filter_rule_key]))
                else:
                    cls.logger.debug("filter_rule_key(%s) not found in %s " % (
                        filter_rule_key, cls.__name__))
            
            # get r/w privilege for each dn for current user
            rules = RulesEngine.execute_rule(dn)
            flt_results = []
            for r in results:
                d = "%s/%s" % (base, r[filter_rule_key])
                if d not in rules:
                    cls.logger.debug("dn(%s) not found in execute_rule" % d)
                else: 
                    access = rules[d]["users"][g.user.username]
                    if access["read"]: flt_results.append(r)
                    else: cls.logger.debug("filtered dn(%s),user:%s" % (
                        d, g.user.username))
            results = flt_results

        # if read_one provided then a single entry should have been found or 
        # user did not have read access to corresponding dn.  Abort with 404
        if read_one is not None:
            if len(results) == 0: 
                cls.logger.debug("%s(%s) not found" % read_one)
                abort(404, "%s(%s) not found" % read_one)
            return results[0]

        # return full list of results
        return {"%s" % cls.__name__.lower():results}

    @classmethod
    def update(cls, collection, **kwargs):
        """ api call to update one entry from collection
            aborts on error, else returns dict reply
            
            Parameters
                collection      - mongo database collection object (required)
                update_one      - tuple in form (key, value) that is used to
                                  update single value from collection(required)
                update_many     - dict filter in mongo format of entries to
                                  update. Note update_one or update_many must
                                  be provided (required)
                su              - super user (boolean) has read/write access
                                  to all attributes. Defaults to False
                rule_dn         - list of rule dns to enforce r/w privilege
                                  if list then rule_match_all attribute to 
                                  decide whether user must match one/all rules
                rule_match_all  - boolean.  Defaults to True
                required_attr   - list of required attributes 
                override_attr   - dict of attribute values that overwrite
                                  any user provided fields.  dict key is 
                                  attribute and value is the override value.

            Return
                update          - dict update inserted into database
        """
        su = kwargs.get("su", False)
        rule_dn = convert_to_list(kwargs.get("rule_dn", None))
        rule_match_all = kwargs.get("rule_match_all", True)
        required_attr = kwargs.get("required_attr", [])
        override_attr = kwargs.get("override_attr", {})
        update_one = kwargs.get("update_one", None)
        update_many = kwargs.get("update_many", None)

        if (not isinstance(update_one, tuple) or len(update_one)!=2) and \
            (update_many is None):
            cls.logger.error("invalid value for update_one arg: %s"%update_one)
            abort(500, "unable to update %s" % cls.__name__ )

        # log update type
        if update_many is not None:
            dm = "update %s/(%s)" % (cls.__name__, update_many)
        else:
            dm = "update %s/(%s/%s)" % (cls.__name__, update_one[0], 
                update_one[1])
        cls.logger.debug("%s user:%s,su:%s,rule:%s,match-all:%r)"%(
            dm, g.user.username, su, rule_dn, rule_match_all))

        # validate user has permission to write to this path.  
        check_user_access(su=su, rules=rule_dn, match_all=rule_match_all, 
            write_required=True, cls=cls)

        # get user data with required parameters 
        data = get_user_data(required_attr)

        # minimum required attributes 
        update = {}
        for a in required_attr: 
            update[a] = force_attribute_type(a, cls.META[a]["type"], data[a], 
                control=cls.META[a])

        # override values (no force_attribute_type check for override)
        for a in override_attr: update[a] = override_attr[a]

        # common practice that user may send key attribute within data for 
        # update although this particular attribute is not writable.  If so,
        # simply remove from data instead of forcing 400 error
        if update_many is None and update_one[0] in data and \
            update_one[0] in cls.META and not cls.META[update_one[0]]["write"]:
            data.pop(update_one[0])

        for a in data:
            # skipping required_attr and override_attr
            if a in required_attr or a in override_attr: continue 
            if a not in cls.META or (not cls.META[a]["write"] and not su):
                    dm = "failed to update '%s', " % cls.__name__
                    dm+= "unknown or invalid attribute '%s'" % a
                    cls.logger.debug(dm)
                    abort(400, dm)
            else:
                update[a] = force_attribute_type(a, cls.META[a]["type"], 
                    data[a], control=cls.META[a])

        # ensure at least one valid attribute provided for user
        if len(update)==0: 
            dm = "failed to update '%s', " % cls.__name__
            dm+= "no valid parameter provided"
            cls.logger.debug(dm)
            abort(400, dm)
        if update_many is not None:
            r = collection.update_many(update_many, {"$set": update})
        else:
            r = collection.update_one({"%s"%update_one[0]:update_one[1]}, {
                "$set": update
            })
        if r.matched_count == 0: 
            cls.logger.debug("%s(%s) not found" % update_one)
            abort(404, "%s(%s) not found" % update_one)

        return update

    @classmethod
    def update_incr(cls, collection, **kwargs):
        """ api call to perform incremental update on one entry from collection
            Different from update, update_incr is only for list attributes and
            expects user provided data to be in following format:
            {
                "attribute": {
                    "add": ['value1', 'value2', ...],
                    "remove": ['value1', 'value2', ...],
                }
            }    

            aborts on error, else returns update dict
            
            Parameters
                collection      - mongo database collection object (required)
                update_one      - tuple in form (key, value) that is used to
                                  update single value from collection (required)
                incr_attr       - list of attributes allowed for incremental 
                                  update. If not supplied then any 'list' 
                                  attribute in META can be used.
                su              - super user (boolean) has read/write access
                                  to all attributes. Defaults to False
                rule_dn         - list of rule dns to enforce r/w privilege
                                  if list then rule_match_all attribute to 
                                  decide whether user must match one/all rules
                rule_match_all  - boolean.  Defaults to True

            Return
                update          - dict update inserted into database
        """
        su = kwargs.get("su", False)
        rule_dn = convert_to_list(kwargs.get("rule_dn", None))
        rule_match_all = kwargs.get("rule_match_all", True)
        incr_attr = convert_to_list(kwargs.get("incr_attr", []))
        update_one = kwargs.get("update_one", None)
        
        if not isinstance(update_one, tuple) or len(update_one)!=2:
            cls.logger.error("invalid value for update_one arg: %s"%update_one)
            abort(500, "unable to update %s" % cls.__name__)

        # get list of possible incremental update attributes for object
        if len(incr_attr)==0:
            for a in cls.META:
                if cls.META[a]["type"] is list and (cls.META[a]["write"] or su):
                    incr_attr.append(a)
        if len(incr_attr)==0:
            dm = "no incremental attributes available for %s" % cls.__name__
            cls.logger.debug(dm)
            abort(400, dm)

        dm = "update_incr %s/(%s/%s)"%(cls.__name__,update_one[0],update_one[1])
        cls.logger.debug("%s user:%s,su:%s,rule:%s,match-all:%r)"%(
            dm, g.user.username, su, rule_dn, rule_match_all))

        # validate user has permission to write to this path.  
        check_user_access(su=su, rules=rule_dn, match_all=rule_match_all, 
            write_required=True, cls=cls)

        # get user data with required parameters 
        data = get_user_data()
        update = {}

        # get incr update values
        for a in incr_attr: 
            if a in data:
                if a not in cls.META or (not cls.META[a]["write"] and not su):
                    dm = "failed to update '%s', " % cls.__name__
                    dm+= "unknown or invalid attribute '%s'" % a
                    cls.logger.debug(dm)
                    abort(400, dm)
                update[a] = {}
                if type(data[a]) is not dict:
                    dm = "%s attribute '%s' should by type 'dict'" % (
                        cls.__name__, a)
                    cls.logger.debug(dm)
                    abort(400, dm)
                for opt in ("add", "remove"):
                    if opt not in data[a]: continue
                    if type(data[a][opt]) is not list:
                        dm = "%s attribute %s[%s] should be type 'list'"% (
                            cls.__name__, a, opt)
                        cls.logger.debug(dm)
                        abort(400, dm)
                    if len(data[a][opt]) == 0: continue
                    update[a][opt] = []
                    subtype=None
                    if "subtype" in cls.META[a]: subtype=cls.META[a]["subtype"]
                    for entry in data[a][opt]:
                        # force entry type and append to update
                        if subtype is not None:
                            entry = force_attribute_type(a, subtype, entry)
                        update[a][opt].append(entry)
                # no validate data provided, pop index
                if len(update[a]) == 0: update.pop(a, None)

        # ensure at least one valid attribute provided for rule
        if len(update)==0: 
            incr_msg = "Expected at least one 'add' or 'remove' attribute"
            cls.logger.debug("No valid parameter provided. %s" % incr_msg)
            abort(400, "No valid parameter provided. %s" % incr_msg)

        # perform add/remove updates
        for a in update:
            cls.logger.debug("performing update on %s: %s" % (a, update[a]))
            if "add" in update[a] and len(update[a]["add"])>0:
                r = collection.update_one({"%s"%update_one[0]:update_one[1]}, {
                    "$addToSet": {a: {"$each": update[a]["add"]}}
                })               
                if r.matched_count == 0: 
                    cls.logger.debug("%s(%s) not found" % update_one)
                    abort(404, "%s(%s) not found" % update_one)
            if "remove" in update[a] and len(update[a]["remove"])>0:
                r = collection.update_one({"%s"%update_one[0]:update_one[1]}, {
                    "$pullAll": {a: update[a]["remove"]}
                })               
                if r.matched_count == 0:
                    cls.logger.debug("%s(%s) not found" % update_one)
                    abort(404, "%s(%s) not found" % update_one)

        # return dict of attribute add/remove values
        return update

    @classmethod
    def delete(cls, collection, **kwargs):
        """ api call - delete rest object, aborts on error. returns delete
            count
            
            Parameters
                collection      - mongo database collection object (required)
                delete_one      - tuple in form (key, value) that is used to
                                  delete single value from collection (required)
                su              - super user (boolean) has read/write access        
                                  to all attributes. Defaults to False
                rule_dn         - list of rule dns to enforce r/w privilege
                                  if list then rule_match_all attribute to 
                                  decide whether user must match one/all rules
                rule_match_all  - boolean.  Defaults to True

            Returns:
                delete_count    - int, number of entries deleted
        """
        su = kwargs.get("su", False)
        rule_dn = convert_to_list(kwargs.get("rule_dn", None))
        rule_match_all = kwargs.get("rule_match_all", True)
        delete_one = kwargs.get("delete_one", None)

        if not isinstance(delete_one, tuple) or len(delete_one)!=2:
            cls.logger.error("invalid value for delete_one arg: %s"%delete_one)
            abort(500, "unable to delete %s" % cls.__name__)

        dm = "delete %s/(%s/%s)"%(cls.__name__,delete_one[0],delete_one[1])
        cls.logger.debug("%s user:%s,su:%s,rule:%s,match-all:%r)"%(
            dm, g.user.username, su, rule_dn, rule_match_all))

        # validate user has permission to write to this path.  
        check_user_access(su=su, rules=rule_dn, match_all=rule_match_all, 
            write_required=True, cls=cls)

        # delete the rule and verify it was deleted
        r = collection.delete_one({"%s"%delete_one[0]:delete_one[1]})
        if r.deleted_count == 0: 
            cls.logger.debug("%s(%s) not found" % delete_one)
            abort(404, "%s(%s) not found" % delete_one)

        return r.deleted_count

def check_user_access(**kwargs):
    """ aborts with 403 message if user does not have necessary access to
        provided rule_dn's.  
    """
    su = kwargs.get("su", False)
    rules = kwargs.get("rules", [])
    match_all = kwargs.get("match_all", False)
    read_required = kwargs.get("read_required", False)
    write_required = kwargs.get("write_required", False)
    cls = kwargs.get("cls", Rest)
     
    # no rules applied for super user (no need to execute rules)
    if su: return
    # no read/write access required at all (no need to execute rules)
    if not read_required and not write_required: return
            
    r = RulesEngine.execute_rule(rules)
    # local user should always be returned in rule, if not then allow
    # exception to occur.  Also, all rule_dn's passed to execute_rule
    # must have r/w attribute per user returned
    match_count = 0
    for dn in rules:
        access = r[dn]["users"][g.user.username]
        if read_required and write_required:
            if access["write"] and access["read"]: match_count+=1
            elif match_all: abort(403, MSG_403)
        elif read_required:
            if access["read"]: match_count+=1
            elif match_all: abort(403, MSG_403)
        elif write_required:
            if access["write"]: match_count+=1
            elif match_all: abort(403, MSG_403)

    # check if any rules were matched
    if match_count == 0:
        abort(403, MSG_403)



# to prevent circular import, RulesEngine is best to be combined with rest
# since Rest objects are primary objects that use engine

class RulesEngine(object):

    # module level logger
    logger = logging.getLogger(__name__)

    @staticmethod
    def execute_rule(dn_list, user_list=[]):
        """ receive one or more dn's and a username and determine 
            read/write privilege for each.
            Args:
                dn_list(list)   dn's to check rule
                user_list(list) username to check against (g.user is always
                                added to user_list even if not provided)
            Returns:
                result(dict): dn-indexed dictionary in following format:
                                {"(dn-rule)":{
                                    "users":{
                                        "(username)": {
                                            "read":bool,
                                            "write":bool
                                        }
                                    }
                                }}
        """
        dn_list = convert_to_list(dn_list)
        if len(dn_list)==0: return {}
        user_list = convert_to_list(user_list)
        users = {}
        users[g.user.username] = {"role": g.user.role,"groups": g.user.groups,
                                  "username": g.user.username}
        if g.user.username in user_list: user_list.remove(g.user.username)
        # need to manually pull role and groups for other users 
        if len(user_list)>0:
            query = {"username":{"$in":user_list}}
            proj = {"username":1,"role":1,"groups":1}
            for r in current_app.mongo.db.users.find(query, proj):
                users[r["username"]] = {
                    "username": r["username"],
                    "role": r["role"],
                    "groups": r["groups"],
                }

        # result dict to return
        results = {}

        # for each dn, build list of dn's that will be search in tree fashion.
        # For example:
        #   /food/fruit/apples/GrannySmith
        #       1) /food/fruit/apples/GrannySmith
        #       2) /food/fruit/apples
        #       3) /food/fruit
        #       4) /food
        #
        # When executing rule, check 'inheritance' flag to see if top rule can
        # be applied to dn with no lower rule.  Longest DN with available rule
        # is used when executing rule.
        cache = {}
        paths = []
        for dn in dn_list:
            path = ""
            results[dn] = {"users":{}, "_p":[], "_c":False}
            for p in dn.strip("/").split("/"):
                path = "%s/%s" % (path, p)
                if path not in cache: 
                    cache[path] = {"rule":None, "result": None}
                results[dn]["_p"].insert(0,path) # longest path first
                paths.append(path)
    
        # lookup all rules matching possible paths
        for r in current_app.mongo.db.rules.find({"dn":{"$in":paths}}):
            if "dn" not in r: continue  # assert/logging later
            if r["dn"] in cache: 
                cache[r["dn"]]["rule"] = r
                cache[r["dn"]]["result"] = None

        # build all_users for implicit permit rule
        all_users = []
        for u in users: all_users.append(u)
        implicit_permit = {"read_users": all_users, "write_users": all_users}

        # execute each rule with cache to prevent redundant rule execution
        for dn in dn_list:
            #RulesEngine.logger.debug("executing rule: %s" % dn)
            rule = None
            p_rules = None # list of parent rules for inheritance
            path_ptr = "/"
            for p in results[dn]["_p"]:
                if rule is not None and p_rules is not None and p in cache:
                    if cache[p]["rule"] is not None:
                        p_rules.append(cache[p]["rule"])
                elif p in cache: 
                    # use cached rule result if already executed
                    if cache[p]["result"] is not None: 
                        results[dn]["users"] = cache[p]["result"]
                        results[dn]["_c"] = True
                        RulesEngine.logger.debug("%s from cache[%s]:%s" % (
                            dn, p, cache[p]["result"]))
                    rule = cache[p]["rule"]
                    path_ptr = p
                    if rule is not None and \
                        (("inherit_read" in rule and rule["inherit_read"]) or \
                        ("inherit_write" in rule and rule["inherit_write"])):
                        p_rules = []

            # check if already completed from cache result
            if results[dn]["_c"]: continue

            # no rule found for dn, set to implicit permit
            if rule is None: 
                #RulesEngine.logger.debug("setting to implicit_permit: %s" % dn)
                rule = implicit_permit

            # expand rule read/write values based on parent rules if applicable
            dn_rule = RulesEngine._expand_rule(rule, p_rules)
            #RulesEngine.logger.debug("expanded rule:%s" % dn_rule)

            # execute rule against each user
            for u in users:
                (read, write) = RulesEngine._execute_rule(users[u], dn_rule)
                results[dn]["users"][u] = {"read":read, "write": write}
                #RulesEngine.logger.debug("result %s, user:%s,r:%r,w:%r" % (
                #    dn,u,read,write))

            # add cache pointer (including '/' for implicit permit)
            cache[path_ptr]["result"] = results[dn]["users"]

        # unset internal variables and return results
        for dn in results:
            results[dn].pop("_c", None)
            results[dn].pop("_p", None)

        return results

    @staticmethod
    def _expand_rule(rule={}, p_rules=[]):
        """ check rule inheritance and expands read/write users/groups based
            on parent rules
            rule - dict with attributes:
                "owner", "inherit_read", "inherit_write", "read_users",
                "write_users", "read_groups", "write_groups"
            p_rules - list of parent rules to inherit from
            
            Returns rule
        """
        if p_rules is None: p_rules = []
        rule = {
            "dn": rule.get("dn", None),
            "owner": rule.get("owner", None),
            "inherit_read": rule.get("inherit_read", False),
            "inherit_write": rule.get("inherit_write", False),
            "read_users": rule.get("read_users", []),
            "write_users": rule.get("write_users", []),
            "read_groups": rule.get("read_groups", []),
            "write_groups": rule.get("write_groups", []),
        }
        # join read/write values with parents if inhert enable
        # (note, p_rules already order by longest-path-first)
        cr = rule
        for pr in p_rules:
            if not cr["inherit_read"] and not cr["inherit_write"]: break
            pr = {
                "dn": pr.get("dn", None),
                "owner": pr.get("owner", None),
                "inherit_read": pr.get("inherit_read", False),
                "inherit_write": pr.get("inherit_write", False),
                "read_users": pr.get("read_users", []),
                "write_users": pr.get("write_users", []),
                "read_groups": pr.get("read_groups", []),
                "write_groups": pr.get("write_groups", []),
            }
            # append 'owner' to both read and write 
            if cr["inherit_write"]:
                rule["write_users"] = combine_list(rule["write_users"], 
                                        pr["write_users"])
                rule["write_groups"] = combine_list(rule["write_groups"], 
                                        pr["write_groups"])
                if pr["owner"] is not None:
                    rule["write_users"] = combine_list(rule["write_users"],
                                            [pr["owner"]])
            if cr["inherit_read"]:
                rule["read_users"] = combine_list(rule["read_users"], 
                                        pr["read_users"])
                rule["read_groups"] = combine_list(rule["read_groups"], 
                                        pr["read_groups"])
                if pr["owner"] is not None:
                    rule["read_users"] = combine_list(rule["read_users"],
                                            [pr["owner"]])
                # if user had write access to parent than it implied read 
                # access, therefore, pull down parent's write into cr read
                rule["read_users"] = combine_list(rule["read_users"], 
                                        pr["write_users"])
                rule["read_groups"] = combine_list(rule["read_groups"], 
                                        pr["write_groups"])

            # disable pr read/write inherit if cr does not allow inherit
            if not cr["inherit_read"]: pr["inherit_read"] = False
            if not cr["inherit_write"]: pr["inherit_write"] = False
            cr = pr

        return rule

    @staticmethod
    def _execute_rule(user, rule):
        """ check user against provided rule and read/write access tuple

            Return tuple (read=boolean, write=boolean)
        """
        # admin role has access to everything, blacklist has access to nothing
        user = {
            "username": user.get("username", ""),
            "role": user.get("role", Roles.BLACKLIST),
            "groups": user.get("groups", []),
        }
        if user["role"] == Roles.FULL_ADMIN: return (True, True)
        elif user["role"] == Roles.BLACKLIST: return (False, False)

        read = False
        write = False

        # check if user has write access (write access forces read=True)
        if user["username"] is not None:
            if user["username"] == rule["owner"]: return (True, True)
            if user["username"] in rule["write_users"]: write = True
            if user["username"] in rule["read_users"]: read = True
        if not write:
            for gp in user["groups"]:
                if gp in rule["write_groups"]: write = True
                if gp in rule["read_groups"]: read = True
        if write: read = True 
        return (read,write)
