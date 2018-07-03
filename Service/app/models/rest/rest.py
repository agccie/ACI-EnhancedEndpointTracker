
import logging, re, copy, time, traceback
from flask import abort, g, jsonify
from ..utils import (hash_password, aes_encrypt, aes_decrypt, MSG_403,
                    get_user_data, get_user_params, get_db)
from pymongo.errors import (DuplicateKeyError, PyMongoError)
from pymongo import (ASCENDING, DESCENDING)
from bson.objectid import ObjectId, InvalidId
from werkzeug.exceptions import (NotFound, BadRequest)
from .dependency import RestDependency
from .role import (Role, api_read_roles)
from swagger.common import (swagger_create, swagger_read, swagger_update,
                            swagger_delete, swagger_generic_path)

root = RestDependency(None)
registered_classes = {}     # all register classes indexed by classname


def api_register(path=None, root_path=None, parent=None):
    """ register REST class with API.  options:
            path    custom api path relative to api blueprint. if not set then 
                    path is set to classname. I.e., if class is Bar in package
                    Foo, then classname is set to <api-blueprint>/foo/bar

            root_path   by default the keyed_path is appended to 'path' value. For objects with no
                    parent it might be undesirable to include path/classname for the keyed_path.
                    Set an optional root_path string to change the keyed_path. This is only used by
                    classes without parent

            parent  classname of parent object. When parent is set then key path
                    is relative to parent and keys are inherited from parent.
                    shortname can still be provided to influence the keypath
                    bulk path:
                        <classname path>
                    key path:
                        <parent-key-path>/<path>/keys
                        or
                        <parent-key-path>/<shortname>-key1/.../keyn
        
            If parent is set then creation of object is blocked if parent does
            not exist. Similarly, if parent is deleted, then all child objects
            are deleted.
    """
    def decorator(cls):
        # stage for registration 
        _cname = cls.__name__.lower()
        if _cname not in registered_classes: 
            # create dependency node for class
            node = RestDependency(cls, root_path=root_path, path=path)
            if parent is None: root.add_child(node)
            else: 
                node.set_parent_classname(parent)
                root.add_loose(node)
            registered_classes[_cname] = cls
        return cls
    return decorator

def register(api):
    """ register routes for each class with provided api blueprint
        and build per-object swagger definition
    """

    # first handle object dependencies sitting in RestDependency root
    root.build()
    for node in root.get_ordered_objects():
        c = node.obj
        c._dependency = node
        c.init()
        parent = None
        if node.parent is not None and node.parent.obj is not None:
            parent = node.parent.obj
        keys = {}   # dict of keys per key_index
        for attr in c._attributes:
            if c._attributes[attr]["key"] and (parent is None or \
                (parent is not None and attr not in parent._keys)):
                _type = c._attributes[attr]["type"]
                _index = c._attributes[attr]["key_index"]
                if _index not in keys: keys[_index] = {}
                key_type = c._attributes[attr]["key_type"]
                if key_type in ["string","int","float","path","any","uuid"]:
                    keys[_index][attr] = "<%s:%s>" % (key_type, attr)
                elif _type is str: keys[_index][attr] = "<string:%s>" % attr
                elif _type is int: keys[_index][attr] = "<int:%s>" % attr
                elif _type is float: keys[_index][attr] = "<float:%s>" % attr
                else:
                    c.logger.error("invalid type for key: [%s, %s, %s]" % (
                        c.__name__, attr, _type))
                    continue
                if c._access["keyed_path"]:
                    if len(c._attributes[attr]["key_sn"])>0: 
                        keys[_index][attr] = "%s-%s" % (c._attributes[attr]["key_sn"], 
                                keys[_index][attr])
                    else:
                        keys[_index][attr] = "%s-%s" % (attr, keys[_index][attr])

        # build list of keys sorted first by index
        key_string = [] 
        for _index in sorted(keys):
            key_string+= [keys[_index][attr] for attr in sorted(keys[_index])]
        key_string = "/".join(key_string)

        # create CRUD rules with default paths
        # create key path and swagger key paths
        path = "/%s" % "/".join(c._classname.split("."))
        if parent is None:
            if len(key_string)>0:
                if node.root_path is not None and len(node.root_path)>0:
                    key_path = "%s/%s" % (node.root_path, key_string)
                else:
                    key_path = "%s/%s" % (path, key_string)
            else:
                if node.root_path is not None and len(node.root_path)>0:
                    key_path = node.root_path
                else:
                    key_path = path
        else:
            key_path = "%s/%s" % (parent._key_path, key_string)
        # remove duplicate slashes from all paths
        path = re.sub("//","/", path)
        key_path = re.sub("//","/", key_path)
        key_swag_path = re.sub("<[a-z]+:([^>]+)>",r"{\1}", key_path)
        c._key_path = key_path
        c._key_swag_path = key_swag_path
        c._swagger = {}

        # add create path
        if c._access["create"]:
            endpoint = "%s_create" % c.__name__.lower()
            api.add_url_rule(path, endpoint , c.api_create, methods=["POST"])
            c.logger.debug("registered create path: POST %s" % path)
            if path not in c._swagger: c._swagger[path] = {}
            swagger_create(c, path)

        # create path will not have _id but read, update, and delete will 
        # include _id as key (if enabled)
        if c._access["expose_id"]: 
            key_path = "%s/%s" % (key_path, "<string:_id>")
            key_swag_path = re.sub("<[a-z]+:([^>]+)>",r"{\1}", key_path)

        # add read paths
        if c._access["read"]:
            if key_path is not None:
                endpoint = "%s_read" % c.__name__.lower()
                api.add_url_rule(key_path, endpoint, c.api_read,methods=["GET"])
                c.logger.debug("registered read path: GET %s" % key_path)
                swagger_read(c, key_swag_path, bulk=False)

            if c._access["bulk_read"] and key_path!=path:
                endpoint = "%s_bulk_read" % c.__name__.lower()
                api.add_url_rule(path,endpoint, c.api_read, methods=["GET"])
                c.logger.debug("registered bulk read path: GET %s" % path)
                swagger_read(c, path, bulk=True)

        # add update paths
        if c._access["update"]:
            if key_path is not None:
                endpoint = "%s_update" % c.__name__.lower()
                api.add_url_rule(key_path,endpoint,c.api_update,
                    methods=["PATCH","PUT"])
                c.logger.debug("registered update path: PATCH,PUT %s"%(
                    key_path))
                swagger_update(c, key_swag_path, bulk=False)

            if c._access["bulk_update"] and key_path!=path:
                endpoint = "%s_bulk_update" % c.__name__.lower()
                api.add_url_rule(path,endpoint,c.api_update,
                    methods=["PATCH","PUT"])
                c.logger.debug("registered bulk update path: PATCH,PUT %s"%(
                    path))
                swagger_update(c, path, bulk=True)

        # add delete paths
        if c._access["delete"]:
            if key_path is not None:
                endpoint = "%s_delete" % c.__name__.lower()
                api.add_url_rule(key_path,endpoint,c.api_delete,
                    methods=["DELETE"])
                c.logger.debug("registered delete path: DELETE %s"%key_path)
                swagger_delete(c, key_swag_path, bulk=False)

            if c._access["bulk_delete"] and key_path!=path:
                endpoint = "%s_bulk_delete" % c.__name__.lower()
                api.add_url_rule(path,endpoint,c.api_delete,methods=["DELETE"])
                c.logger.debug("registered bulk delete path: DELETE %s"%path)
                swagger_delete(c, path, bulk=True)

        # handle custom routes
        for r in c._access["routes"]:
            if "function" not in r or not callable(r["function"]):
                c.logger.warn("%s skipping invalid route: %s, bad function"%(
                    c._classname, r))
                continue
            if "path" not in r or len(path)==0:
                c.logger.warn("%s skipping invalid route: %s, bad path"%(
                    c._classname, r))
                continue
            if "keyed_url" in r and r["keyed_url"]: 
                rpath = "%s/%s"%(key_path, re.sub("(^/+)|(/+$)","",r["path"]))
            else: 
                rpath = "%s/%s"%(path, re.sub("(^/+)|(/+$)","",r["path"]))

            methods = []
            if "methods" in r and isinstance(r["methods"], list):
                for m in r["methods"]:
                    if m not in ["GET","DELETE","POST","PATCH","PUT"]:
                        c.logger.warn("%s invalid method: (%s) %s" % (
                            c._classname, r, m))
                        continue
                    if m not in methods: methods.append(m)
                if len(methods)==0:
                    c.logger.warn("%s no valid methods %s" % (
                        c._classname, r))
                    continue
            else: methods=["GET"]
            endpoint="%s_%s" % (c.__name__.lower(), r["function"].__name__)
            api.add_url_rule(rpath, endpoint,r["function"],methods=methods)
            c.logger.debug("registered custom path: %s %s"%(methods, rpath))
            # for custom routes just add optional summary if present
            summary = r.get("summary", "")
            if len(summary) == 0: summary = r["function"].__doc__
            swag_rpath = re.sub("<[a-z]+:([^>]+)>",r"{\1}", rpath)
            swagger_generic_path(c,swag_rpath,methods[0],summary)



class Rest(object):
    """ generic REST object providing common rest functionality.  All other 
        REST model objects should inherit this class and overwrite 
        functionality as needed.  

        Common functions include:
            Rest.create(_data)
            Rest.read(_params)
            Rest.update(_data, _params)
            Rest.delete(_params)

            # load an object from database based on key attributes
            object = Rest.loads(**kwargs)

            # get dict/json representation of object
            js = object.to_json()

            # determine if loaded object currently exists in database
            object.exists() 

            # save current object with any attributes changes to database
            object.save()

            # remove object from database. Similar to delete but delete is
            # a classmethod to delete multiple entries from database whereas
            # remove deletes only currently referenced object
            object.remove()     
    
        # optional callback kwargs
        callback functions will receive all kwargs that CRUD function received.
        The kwargs will contain keys for the object for non-bulk 
        read/update/delete operations. Additionall, kwargs may include the 
        following:
            __api = boolean             # request from api event
            __read_all = boolean        # allow all attribute to be read
            __write_all = boolean       # allow all attributes to be written

        All classes require META_ACCESS with following:

        {

            "expose_id":    bool, expose mongo's inherit _id ObjectId which is
                                an implicit key. When true, and _id attribute 
                                is available as an additional key used for 
                                read, update, and delete operations. 
                                Default False
            "keyed_path":   bool, (default true) include key name in within path.  For example, for
                            a classname User with keys 'username' and 'group' and keyed_path 
                            enabled, the path for user dn would be:
                                /api/user/username-<username>/groups-<group>
                            without keyed_path enabled the dn would be:
                                /api/user/<username>/<groups>
            "dn":           bool, (default true) include a distinguished name (dn) property in read
                            requests for an object
            "read_role":    int, role required to perform read operations
                                 default Role.USER
            "write_role":   int, role required to perform write operations
                                 default Role.FULL_ADMIN
            "execute_role": int, role required to perform execute operations
                                 default Role.FULL_ADMIN
            "create":       bool, enable create api, default True
            "read":         bool, enable read and bulk read api, default True
            "update":       bool, enable update api, default True
            "delete":       bool, enable delete api, default True
            "bulk_read":    bool, allow for bulk read of objects within class 
                                  along with optional attribute filters. 
                                  defaults True.
                                  if read is disabled then bulk_read is also
                                  implicitly disabled
            "bulk_update":  bool, allow to update bulk objects for class with
                                  optional attribute filters.  default False
                                  value is applied at API creation
                                  if update is disabled then bulk_update is also
                                  implicitly disabled
            "bulk_delete":  bool, allow to delete bulk objects for class with
                                  optional attribute filters.  default False
                                  value is applied at API creation
                                  if delete is disabled then bulk_delete is also
                                  implicitly disabled
            "before_create": function, before a create request the data is 
                                  provided for additionally updates. The 
                                  function must return a dict to be inserted
                                  into the db. 
                                    new_data = before_create(data, **kwargs)
            "before_read":  function, before a read request is perform, the db
                                  filter can be run through the provided 
                                  callback function to update the filter. The 
                                  function must accept a dict filter and return
                                  the updated dict.
                                    new_filter = before_read(filters, **kwargs)
            "before_update": function, before an update occurs, the filter and
                                  data parameters are provided to a callback
                                  function that must return a tuple with the
                                  update filter and updated data
                                    (new_filter, new_data) = before_update(
                                        filters, data, **kwargs)
            "before_delete": function, before a delete occurs, the filter is
                                  provided to a callback function that can alter
                                  the filter
                                        new_filter = before_delete(filters, 
                                            **kwargs)
            "after_create":  function, after a successful create, the created 
                                  object is provided to callback function
                                    after_create(data)
            "after_read":   function, after a read request is perform, the 
                                  return dict object (containing 'count' and 
                                  'objects') is sent through provided function
                                  to alter results. This function SHOULD return
                                  a dict with count and objects attributes to be
                                  consistent with other rest objects but is not
                                  required.
                                    new_results = after_read(results, **kwargs)
            "after_update": function, after an update occurs, the corresponding
                                  filter and update data is provided to callback
                                  function.
                                    after_update(filter, data, **kwargs)
            "after_delete": function, after a delete occurs, the corresponding
                                  filter is provided to a callback function
                                    after_delete(filter, **kwargs)

            "routes":       list of custom (non-CRUD) routes to provide to API.
                            each route is a dict with the following options:
                
                    "path":     str, string url path with corresponding args
                                required by endpoint function. This path is 
                                appended with the corresponding path to the 
                                classname. For example, User class located at
                                /api/user can add a 'login' path which will be
                                pushed to /api/user/login

                    "keyed_url" bool, if true then path will include object
                                keys before appending provided path. For 
                                example, User class located at /api/user with
                                key "<string:username>" could have a 'login'
                                path requiring key in the url resulting in the
                                    path: /api/user/<string:username>/login
                                    or (if keyed_path is enabled under META_ACCESS)
                                    path: /api/user/username-<string:username>/login
                    
                    "function"  func, function to accept route

                    "methods":  list, methods for route. Defaults to "GET". 
                                support for "GET", "DELETE", "POST", "PATCH",
                                and "PUT"

                    "summary":  str, swagger doc summary
        }

        All classes required META dict in following format:
        {

            "attribute1": {
                "type":     [str|bool|dict|list|int|float], default str
                "default":  default value if not provided, default None
                "read":     bool, allow read access to attribute.  default True
                "write":    bool, allow write access to attribute. default True
                "key":      bool, this is part of object key.  default False
                "key_type": str, to override API routing type, key type can be 
                            set to one of the following supported converters:
                            string, int, float, path, any, uuid
                "key_index": int, when multiple keys are provided, the key index
                            determines order of keys in api URL along with order
                            of keys in kwargs. The lower ordered indexes will
                            be presented first. keys with the same index are 
                            sorted alphabetically. By default all keys have 
                            key_index of 0.
                "key_sn":   str, key shortname used only when keyed_path is enabled
                            under META_ACCESS.  This allows for a shorthand name for the
                            corresponding key.  For example, a key attribute with name
                            'fabric_id' could have a key_sn set to 'fid' and the API url
                            for the corresponding object would use 'fid' in the dn.
                "description": str, a description of the attribute for
                            documentation purposes only
                "encrypt":  bool, the value is encrypted before storing in db
                            and decrypted on read. Note encryption happens 
                            after validation.  default False.
                "hash":     bool, the value is encypted via one-way hash before
                            storing in database.  default is False.
                            If both encrypt and hash is enabled, then encrypt
                            takes precedence
                
                (optional controls on create/update)
                "regex":    str, regex validator
                "min":      int/float, minimum value validator
                "max":      int/float, maximum value validator
                "values":   list, list of allowed values for attribute
                "subtype":  [str|bool|dict|tuple|int|float]
                            for list, a subtype validator can be specified to 
                            ensure *all* values within list are the same type
                            and casted corrected.  Note, subtype can be used 
                            with other validators which will apply to the 
                            elements within the list
                "meta":     dict, if attribute is type dict (or subtype is type
                            dict), then metadata can be provided for the 
                            expected attributes in the dict. All controls
                            for an attribute are supported for sub-attributes 
                            specified in meta allowing for complex objects, 
                            except for the following:
                                - key 
                                - read
                                - write
                                - encrypt
                                - hash
                "formatter": func, custom formatter function to format the user
                             provide value after successfully casted but before
                             validation against regex/min/max/values. Example,
                             an attribute of type string may require all lower-
                             case values but allow user to send uppercase and
                             have backend change to lowercase.
                             formatter function must accept a single argument,
                             the value to format, and return the formatted value
                "validator": func, custom validator function to validate the
                            attribute. validator function must accept following
                            keyward arguments:
                                - classname         : str classname
                                - attribute_name    : str attribute name
                                - attribute_meta    : attribute meta dict
                                - value             : user provided value  
                            and return formatted value or abort with 400 error
                            and appropriate error message if value is invalid
            },
            "attribute2": {... },
        }
    """

    logger = logging.getLogger("app.models.rest")
    META = {}
    META_ACCESS = {}
    DEFAULT_PAGE_SIZE = 10000
    MAX_PAGE_SIZE = 75000
    MAX_RESULT_SIZE = 50000000
    ACCESS_DEF = {
        "expose_id": False,
        "keyed_path": True,
        "dn": True,
        "read_role": Role.USER,
        "write_role": Role.FULL_ADMIN,
        "execute_role": Role.FULL_ADMIN,
        "create": True,
        "read": True,
        "update": True,
        "delete": True,
        "bulk_read": True,
        "bulk_update": False,
        "bulk_delete": False,
        "before_create": None,
        "before_read": None,
        "before_update": None,
        "before_delete": None,
        "after_create": None,
        "after_read": None,
        "after_update": None,
        "after_delete": None,
        "routes": [],
    }
    ATTRIBUTE_DEF = {
        "type": str,
        "default": None,
        "read": True,
        "write": True,
        "key": False, 
        "key_type": None,      
        "key_index": 0,
        "key_sn": "",
        "description": "",
        "encrypt": False,
        "hash": False,
        "regex": None,
        "min": None,
        "max": None,
        "values": None,
        "subtype": None,
        "meta": None,
        "formatter": None,
        "validator": None ,
    }
    _access = {}
    _attributes = {}
    _keys = []          # list of attribute keys
    _class_init = False
    _dependency = None
    _classname = ""
    _key_path = ""
    _key_swag_path = ""
    _swagger = {}       # dict of endpoints types added during registration
                        # used only by swagger docs
    _dn_path = ""       # when dn is enabled on object, this is fmt string used for dn.  I.e.,
                        #   /base/uname-%s/group-%s
    _dn_attributes = [] # when dn is enabled on object, this is fmt attribute names used for dn:
                        #   ['username', 'group'] for substituting /base/uname-%s/group-%s

    operator_reg= "^[ ]*(?P<op>[a-z]+)[ ]*\((?P<data>.+)\)[ ]*$" 
    operand_reg = '^(?P<delim>[ ]*,?[ ]*)('
    operand_reg+= '(?P<str>".*?(?<!\\\\)")|'
    operand_reg+= '(?P<float>-?[0-9\.]+)|'
    operand_reg+= '(?P<bool>true|false)|'
    operand_reg+= '(?P<op>[a-z]+\()'
    operand_reg+= ')'

    def __init__(self, **kwargs):
        """ per-object initialization. Allows for any attribute to be provided
            via kwargs.  If not provided then default is applied 
        """ 
        self.init()     # class initialization if not already initialized
        self._exists = False            # true if read from db (via Rest.load)
        self._original_attributes = {}  # original attribute default values
                                        # used to determine which values have 
                                        # changed at save()

        for attr in self._attributes:
            d = self.get_attribute_default(attr)
            if not self._attributes[attr]["key"]:
                self._original_attributes[attr] = d
            if attr in kwargs: setattr(self, attr, kwargs[attr])
            else: setattr(self, attr, d)

    def __repr__(self):
        """ string representation of object for debugging 
            do not show encrypt values
        """
        s = "%s" % self._classname
        a = []
        if self._access["expose_id"] and hasattr(self, "_id"):
            a.append("_id:%s"%getattr(self,"_id"))
        for attr in self.__class__._attributes:
            if self.__class__._attributes[attr]["encrypt"]: continue
            if hasattr(self, attr): 
                a.append("%s:%s" % (attr, getattr(self,attr)))
        return "%s{%s}" % (s, ",".join(a))

    def to_json(self):
        """ return json(dict) representation of object """
        js = {}
        for attr in self._attributes:
            if hasattr(self, attr): js[attr] = getattr(self,attr)
        if self._access["expose_id"] and hasattr(self, "_id"):
            js["_id"]  = getattr(self, "_id")    
        return js

    def exists(self):
        """ determine if the created object already exists in the db 
            this is only relevant if object was created via load function
        """
        return self._exists

    def save(self):
        """ save current instance of object to database.  If does not exists,
            then will attempt a create.  If already exists, then will perform
            an update.  
            Returns boolean success
        """
        obj = {}
        try:
            # perform create if this object does not currently exists
            if not self.exists(): 
                for attr in self._attributes:
                    if hasattr(self, attr): obj[attr] = getattr(self,attr)
                ret = self.create(_data=obj, __write_all=True)
                if self._access["expose_id"] and "_id" in ret: 
                    self._id = ret["_id"]
                self._exists = True
            # perform update for existing object only providing changed values
            else:
                keys = self.get_keys()
                keys["__write_all"] = True
                for attr in self._attributes: 
                    if hasattr(self, attr):
                        if attr in self._original_attributes and \
                            self._original_attributes[attr]==getattr(self,attr):
                            continue
                        obj[attr] = getattr(self, attr)
        
                # only perform update if length of update is > 0, else 400 error
                if len(obj)>0:  self.update(_data=obj, **keys)

            # reset all current _original_attributes to current value so 
            # subsequent saves correctly reflect current state
            for attr in self._original_attributes: 
                if hasattr(self, attr): 
                    self._original_attributes[attr] = copy.deepcopy(
                        getattr(self, attr))
            return True 
        except Exception as e:
            self.logger.warn("%s save failed: %s" % (self._classname, e))
        return False

    def remove(self):
        """ remove current instance of object from database. No check on whether
            object already exists or not, simply perform delete operation.
            Return boolean success. If modified count is 0 then entry did not
            exists and therefore remove is also successful...
        """
        keys = self.get_keys()
        try:
            ret = self.__class__.delete(**keys)
            return True
        except Exception as e:
            self.logger.warn("%s remove failed: %s" % (self._classname, e))
        return False

    def get_keys(self):
        """ return dict of current key and values for this object """
        keys = {}
        for attr in self.__class__._attributes:
            if self.__class__._attributes[attr]["key"]:
                if hasattr(self, attr): keys[attr] = getattr(self, attr)
                else: 
                    keys[attr] = self.__class__.get_attribute_default(attr)
        if self._access["expose_id"] and hasattr(self, "_id"):
            keys["_id"] = self._id
        return keys

    @classmethod
    def load(cls, **kwargs):
        """ initialize an instance of the rest object where all Meta values
            are object attributes.  Value is found by performing read for 
            provided keys.  If more than one object is found than the first
            object is used.  If no objects are found then all attributes will
            have default values.
            This function sets the _exists flag to true for the instantiated
            object if found
        """
        obj = cls(**kwargs)
        db_obj = {}
        try:
            kwargs["__read_all"] = True
            ret = cls.read(**kwargs)
            if "objects" in ret and isinstance(ret["objects"], list) and \
                len(ret["objects"])>0 and cls._classname in ret["objects"][0]:
                db_obj = ret["objects"][0][cls._classname]
                obj._exists = True
        except NotFound as e:
            cls.logger.debug("%s load not found: %s" % (cls._classname,e))
        except Exception as e:
            cls.logger.debug("traceback: %s" % traceback.format_exc())
            cls.logger.warn("%s load failed: %s" % (cls._classname, e))

        for attr in cls._attributes:
            if attr in db_obj:
                # override original attributes to represent original db state
                obj._original_attributes[attr] = copy.deepcopy(db_obj[attr])
                # update return object with db value if not in kwargs
                if attr not in kwargs: setattr(obj, attr, db_obj[attr])
        if cls._access["expose_id"] and "_id" in db_obj:
            setattr(obj, "_id", db_obj["_id"])
        return obj

    @classmethod
    def get_attribute_default(cls, attr):
        """ return default value for an attribute.
            return None if attributes is unknown
        """
        v = None
        if attr in cls._attributes:
            if cls._attributes[attr]["type"] is list: return []
            v = cls._attributes[attr]["default"]
            if cls._attributes[attr]["type"] is dict:
                v = cls.validate_attribute(attr, {})
        return v

    @classmethod
    def init(cls):
        """ update class _access and _attributes based on meta data """
        if cls._class_init: return
        cls._class_init = True
        cls._access = {}
        cls._attributes = {}
        cls._keys = []
        if cls._dependency.path is None:
            cls._classname = re.sub("_",".", cls.__name__).lower()
        else:
            path = re.sub("(^/+)|(/+$)","", cls._dependency.path)
            cls._classname = re.sub("/",".", path).lower()
        cls.logger.debug("initializing class %s" % cls._classname)
        # for each access attribute, ensure all def values are present
        for d in cls.ACCESS_DEF:
            if d not in cls.META_ACCESS: 
                cls._access[d] = copy.copy(cls.ACCESS_DEF[d])
            else: cls._access[d] = cls.META_ACCESS[d]
        # no support for expose_id with parent dependency
        if cls._dependency.parent is not None and cls._access["expose_id"]:
            raise Exception("no support for expose_id with dependencies")

        def init_attribute(attr, sub=False):
            base = {}
            for d in cls.ATTRIBUTE_DEF:
                if sub and d in ["key","read","write","encrypt", "hash"]: 
                    continue
                if d in attr: base[d] = attr[d]
                else: base[d] = copy.copy(cls.ATTRIBUTE_DEF[d])

            # handle meta for dict type or list with subtype dict
            if base["type"] is dict or (base["type"] is list and \
                base["subtype"] is dict):
                if not isinstance(base["meta"], dict): base["meta"] = {}
                for m in base["meta"]:
                    base["meta"][m] = init_attribute(base["meta"][m],sub=True)

            # set default value if not present
            if base["default"] is None:
                if base["type"] is dict or (base["type"] is list and \
                    base["subtype"] is dict): 
                    sv = {}
                    for m in base["meta"]:
                        sv[m] = base["meta"][m]["default"]
                else:
                    base["default"] = {
                        str: "",
                        int: 0,
                        float: 0.0,
                        bool: False,
                        list: [],
                        dict: {},
                    }.get(base["type"], None)
            return base

        # for each attribute, ensure all def values are present
        for a in cls.META:
            if type(cls.META[a]) is not dict: 
                cls.logger.warn("%s invalid meta attribute %s: %s" % (
                    cls._classname, a, cls.META[a]))
            # ignore any top level attribute that begins with an underscore
            if a[0] == "_":
                cls.logger.error("%s unsupported parameter name %s" % (
                    cls._classname, a))
                continue 
            cls._attributes[a] = init_attribute(cls.META[a])
            if cls._attributes[a]["key"]: cls._keys.append(a)

        # copy over parent keys as implicit keys for this object.
        # abort if parent (or grandparent) and child have overlapping keys
        if cls._dependency.parent is not None and cls._dependency.parent.obj is not None:
            parent = cls._dependency.parent.obj
            for k in parent._keys:
                if k in parent._attributes:
                    cls.logger.debug("adding implicit parent key '%s'",k)
                    if k in cls._attributes:
                        raise Exception("%s inherited key '%s' overlaps with existing attribute"%(
                            cls._classname, k))
                    cls._attributes[k] = copy.deepcopy(parent._attributes[k])
            cls._keys = parent._keys + cls._keys


    @classmethod
    def authorized(cls):
        """ abort if user is not authorized (not currently logged in) """
        if not g.user.is_authenticated: abort(401, "Unauthorized")
        
    @classmethod
    def rbac(cls, action="read"):
        """ execute rbac/rule to verify user has access to resource
            raise 403 for unauthorized access attempt
        """
        # perform role check
        role = {
            "read": cls._access["read_role"],
            "write": cls._access["write_role"],
            "execute": cls._access["execute_role"],
        }.get(action, Role.FULL_ADMIN)
        cls.authorized()
        if g.user.role > role: abort(403, MSG_403)

    @classmethod
    def api_create(cls):
        """ api call - create rest object, aborts on error """
        cls.rbac(action="write")
        _data = get_user_data()
        ret = cls.create(_data=_data, _api=True)
        # pop _id as this is not exposed by default on api create operations
        if not cls._access["expose_id"]: ret.pop("_id", None)
        return jsonify(ret)

    @classmethod
    def api_read(cls, **kwargs):
        """ api call - read rest object, aborts on error """
        cls.rbac(action="read")
        _params = get_user_params()
        kwargs["_api"] = True
        return jsonify(cls.read(_params=_params, **kwargs))

    @classmethod
    def api_update(cls, **kwargs):
        """ api call - update rest object, aborts on error """
        cls.rbac(action="write")
        _data = get_user_data()
        _params = get_user_params()
        kwargs["_api"] = True
        return jsonify(cls.update(_data=_data, _params=_params, **kwargs))

    @classmethod
    def api_delete(cls, **kwargs):
        """ api call - update rest object, aborts on error """
        cls.rbac(action="write")
        _params = get_user_params()
        kwargs["_api"] = True
        return jsonify(cls.delete(_params=_params, **kwargs))

    @classmethod
    def validate_attribute(cls, attr, val):
        """ receive attribute name and use provided value and return validated
            value casted to the correct type with appropriate defaults.
            If value is invalid then abort with 400 code and appropriate error
        """

        def raise_error(classname, attr, val, e=""):
            if len(e)>0: e = ". %s" % e 
            abort(400, "%s.%s invalid value '%s'%s"%(classname,attr,val, e))

        def default_validator(**kwargs):
            classname = kwargs.get("classname", "<class>")
            attribute_name = kwargs.get("attribute_name", "<attribute>")
            a = kwargs.get("attribute_meta", {})
            value = kwargs.get("value", None)
            original_value = value

            # check for custom validator for attribute first
            validator = a.get("validator", None)
            if callable(validator):
                return validator(classname=classname, attribute_meta=a,
                    attribute_name=attribute_name, value=value)

            atype   = a.get("type", str)
            values  = a.get("values", None)
            a_min   = a.get("min", None)
            a_max   = a.get("max", None)
            a_regex = a.get("regex", None)
            subtype = a.get("subtype", None)
            meta    = a.get("meta", None)
            index   = 0
            try:
                # if type is a list, then first validate correct type. To allow
                # per-item validation in list, always assume a list and
                # return either list or just first item in the list.
                valid_values = []
                if atype is list :
                    if not isinstance(value, list):
                        raise ValueError("received '%s' but expected a list"%(
                            str(type(value))))
                else: 
                    # perform validation as if attribute was a list, set subtype
                    # to the original attribute type
                    value = [value]
                    subtype = atype

                # perform casting of value only for following primitives:
                #   str, float, int, bool, dict, list
                if subtype not in [str, float, int, bool, dict, list]:
                    cls.logger.warn("unable to validate %s.%s type %s" % (
                        classname, attribute_name, subtype))
                    valid_values = value
                else:
                    for index, pre_v in enumerate(value):
                        # cast pre-value to attribute type allowing ValueError
                        if subtype is str and (isinstance(pre_v, str) or \
                            isinstance(pre_v,unicode)):
                            # encode without casting to support utf-8 chars
                            v = pre_v.encode('utf-8')
                        elif subtype is bool:
                            # support string 'True' and 'False' for bools along
                            # with int/float 1 or 0.  For any other value raise
                            # ValueError
                            if isinstance(pre_v, bool): 
                                v = bool(pre_v)
                            elif isinstance(pre_v,float) or \
                                isinstance(pre_v,int):
                                v = int(pre_v)
                                if v!=0 and v!=1: raise ValueError()
                                v = bool(v)
                            elif isinstance(pre_v,str) or \
                                isinstance(pre_v,unicode):
                                pre_v = pre_v.lower()
                                if pre_v == "true": v = True
                                elif pre_v == "false": v = False
                                else: raise ValueError() 
                            else: raise ValueError()
                        else: v = subtype(pre_v)

                        # check for formatter function
                        if callable(a.get("formatter",None)): 
                            v = a["formatter"](v)

                        # check if value is in list of values
                        if values is not None and v not in values:
                            e="Value must be one of the following: %s"%(values)
                            raise ValueError(e)

                        # handle type dict by examining per-attribute meta
                        if subtype is dict and meta is not None and len(meta)>0:
                            vv = {}
                            for m in meta:
                                mtype = meta[m].get("type", str)
                                msubtype = meta[m].get("subtype", None)
                                if m in v or mtype is dict or \
                                    (mtype is list and msubtype is dict):
                                    if m not in v:
                                        v[m] = [] if mtype is list else {}
                                    if atype is list:
                                        aname = "%s.%s.%s" % (attribute_name,
                                            index, m)
                                    else: aname = "%s.%s" % (attribute_name, m)
                                    vv[m] = default_validator(
                                        classname=classname, 
                                        attribute_name=aname, 
                                        value = v[m], attribute_meta=meta[m])
                                else: 
                                    vv[m] = meta[m].get("default", None)
                            # ensure any attributes in v not in meta raise error
                            for m in v:
                                if m not in meta:
                                    raise ValueError("unknown attribute '%s'"%m)
                            v = vv
                    
                        # perform min/max check for int/float only
                        if subtype is int or subtype is float:
                            if a_min is not None and v < a_min:
                                raise ValueError("Must be >= %s" %a_min)
                            if a_max is not None and v > a_max:
                                raise ValueError("Must be <= %s" %a_max)

                        # perform regex only for strings
                        if subtype is str and a_regex is not None:
                            if not re.search(a_regex, v): raise ValueError()

                        # value is valid
                        valid_values.append(v)

                # finally single valid value or all values if atype was list
                if atype is list: return valid_values
                elif len(valid_values)>0: return valid_values[0]

            except (ValueError, TypeError) as e: 
                if atype is list: 
                    attribute_name = "%s.%s" % (attribute_name,index)
                raise_error(classname, attribute_name, original_value, 
                    ("%s"%e).strip())

            # should never get error, abort with server error
            abort(500, "unable to validate %s.%s value %s" % (classname,
                attribute_name, original_value))

        # perform validation on attribute
        attribute_meta = cls._attributes.get(attr, None)
        if attribute_meta is None or type(attribute_meta) is not dict:
            cls.logger.error("unknown or invalid attribute: %s" % attr)
            abort(500, "unable to validate attribute %s" % attr)

        return default_validator(classname=cls._classname, 
            attribute_name = attr, value = val, attribute_meta=attribute_meta)
     
    @classmethod
    def filter(cls, f={}, params=None):
        """ parses user provided params to build db filter used for bulk
            read/update/delete operations. Fitler is combined with argument f
            and returned.  Returns None on error

            param filter operators are in the form 'operator(x, y)'. Generally,
            x is an attribute name but can also be other operator objects when
            using the 'and' or 'or' operators 
                and     : logical 'and' of two operators
                or      : logical 'or' of two operators
                eq      : equal (default if no qualifier)
                neq     : not equal
                gt      : greater than
                lt      : less than
                ge      : greater than or equal
                le      : less than or equal
                regex   : perform regex validation against a string attribute

            Example:
            1)  eq(attribute.name, "value1")
            2)  and(
                    or(
                        eq(name, "name1"), 
                        eq(name, "name2")
                    ),
                    gt(count, 5)
                )
        """

        def raise_error(fs, e=""):
            if len(e)>0: e = ". %s" % e 
            cls.logger.debug("invalid filter %s%s" % (fs,e))
            abort(400, "invalid filter %s%s" % (fs, e))

        def parse_operands(fs):
            # receive operand string and return list of comma-separated operands
            operands = []

            # operands MUST be in one of the following structures
            #   1) quoted string
            #   2) float/integer value
            #   3) true/false boolean
            #   4) another (greedy) operator
            #  example:
            #   "string", -23.1153, false, eq(...)
            # ".*?[^\\]?"       = match quoted string checking for escape quotes
            # -?[0-9\.]+        = match float/integer
            # (?i)(true|false)  = match boolean
            # operand_reg pre-compiled within rest object

            original_fs = fs
            #cls.logger.debug("parse operands: [%s]" % original_fs)
            fs = fs.strip()
            while len(fs) > 0:
                #cls.logger.debug("parsing sub-operands: [%s]" % fs)
                r1 = re.search(Rest.operand_reg, fs, re.IGNORECASE)
                if r1 is None: 
                    # occurs with invalid operand only
                    cls.logger.debug("sub-operand not matched")
                    err = "invalid operand or unbalanced parenthesis"
                    raise ValueError(err)
                delim = r1.group("delim")
                #cls.logger.debug("delim: [%s]" % r1.group("delim"))
                if r1.group("str") is not None: 
                    #cls.logger.debug("str: [%s]" % r1.group("str"))
                    operands.append(r1.group("str"))
                    delim+= r1.group("str")
                elif r1.group("float") is not None:
                    #cls.logger.debug("float: [%s]" % r1.group("float"))
                    operands.append(float(r1.group("float")))
                    delim+= r1.group("float")
                elif r1.group("bool") is not None:
                    #cls.logger.debug("bool: [%s]" % r1.group("bool"))
                    if r1.group("bool").lower() == "true": operands.append(True)
                    else: operands.append(False)
                    delim+= r1.group("bool")
                else:
                    # match on operator need to walk each character to account
                    # for embedded operators within it.
                    #cls.logger.debug("op: [%s]" % r1.group("op"))
                    op = delim+r1.group("op")
                    depth = 0
                    for i, c in enumerate(fs[len(op):]):
                        #cls.logger.debug("checking: [%s:%s]" % (i,c))
                        if c==")":
                            if i>0 and fs[i-1]=="\\": continue
                            elif depth>0: depth-=1
                            else:  
                                operands.append("%s%s"%(r1.group("op"),
                                    fs[len(op):len(op)+i+1]))
                                delim+= operands[-1]
                                #cls.logger.debug("op set:[%s]"%operands[-1])
                                break
                        elif c=="(":
                            if i>0 and fs[i-1]=="\\": continue
                            depth+= 1
                    if depth!=0:
                        raise ValueError("unbalanced parathensis")
                
                # remove the delimiter and ensure that if there are any more 
                # characters, they start with a comma ','
                fs = re.sub("^%s" % re.escape(delim), "", fs)
                if len(fs)>0 and not re.search("^[ ]*,", fs):
                    cls.logger.debug("operands not separated by comma: %s"%fs)
                    err = "invalid operand or unbalanced parenthesis"
                    raise ValueError(err)
            return operands

            
        def parse_operator(fs):
            # receives a filter string (fs) and returns mongo filter json
            if len(fs) == 0: return {}
            #cls.logger.debug("parse operator: [%s]" % fs)
            r1 = re.search(Rest.operator_reg, fs, re.IGNORECASE)
            if r1 is None: raise_error(fs)
            operator = r1.group("op").lower()
            try: operands = parse_operands(r1.group("data"))
            except ValueError as e: raise_error(fs, "%s" % e)
            if len(operands) == 0: raise_error(fs)

            #cls.logger.debug("operator: %s, operands: %s"%(operator,operands))
            if operator=="and" or operator=="or":
                op_str = "$%s" % operator
                if len(operands)<2:
                    err = "two or more operands required for '%s'" % operator
                    raise_error(fs, err)
                ret = {op_str: []}
                for o in operands:
                    ret[op_str].append(parse_operator(o))
                return ret
            else:
                # validate supported operator
                if operator not in ["gt","lt","ge","le","eq","neq","regex"]:
                    raise_error(fs, "unknown operator %s" % operator)
                # all other operators must have two operands where first operand
                # is a string representing the attribute name and the second is
                # the value (which can be string, float, or bool)
                if len(operands)!=2: 
                    raise_error(fs, "received %s operands" % (len(operands)))
                # for each operand, remove quotes if string
                for i,o in enumerate(operands):
                    if isinstance(o, str) or isinstance(o, unicode):
                        o = re.sub("(^\")|(\"$)","", o)
                    operands[i] = o
                # check that operand[0] which represents an attribute exists
                # if not, check if it represents a sub object in list/dict
                if operands[0] not in cls._attributes:
                    meta = cls._attributes
                    metatype = dict
                    for attr in operands[0].split("."):
                        if attr in meta:
                            metatype = meta[attr].get("type", str)
                            meta = meta[attr].get("meta", {})
                            if not isinstance(meta,dict): meta = {}
                        elif metatype is list and re.search("^[0-9]+$",attr):
                            metatype = None # only allow list match once
                        else:
                            raise_error(fs,"unknown attribute %s"%operands[0])
                # build filter based on operator
                if operator == "eq": return { operands[0]: operands[1]}
                elif operator == "regex":
                    # validate regex is valid 
                    try: re.compile(operands[1])
                    except re.error as e: raise_error(fs, "%s" % e)
                op_str = {
                    "eq": "$eq",
                    "gt": "$gt",
                    "ge": "$gte",
                    "lt": "$lt",
                    "le": "$lte",
                    "neq": "$ne",
                    "regex": "$regex",
                }.get(operator, "eq")
                return {operands[0]: { op_str: operands[1]}}
            
        if params is None: params = get_user_params()
        user_filter = params.get("filter","").strip()
        if len(user_filter)>0:
            cls.logger.debug("parse user filter: %s" % user_filter)
            r = parse_operator(user_filter)
            if len(r)>0: cls.logger.debug("parsed filter: %s" % r)
            for k in r: f[k] = r[k]
        return f

    @classmethod
    def create(cls, _data, **kwargs):
        """ create new rest object, aborts on error.

            Return dict of with following attributes:
                success:    boolean success flag
                count:      total number of objects updated
                _id:        string objectId of inserted object
        """
        cls.init()
        classname = cls._classname
        cls.logger.debug("%s create request" % classname)
        collection = get_db()[classname]

        # allow write to attribute indepdent of whether write is true or false
        _write_all = kwargs.get("__write_all", False)

        obj = {}
        ret_obj = {"success": True, "count":1, "_id":""}
        keys = {}
        for attr in cls._attributes:
            a = cls._attributes[attr]
            atype       = a.get("type", str)
            default     = a.get("default", None)
            write       = a.get("write", True)
            key         = a.get("key", False)
            encrypt     = a.get("encrypt", False)
            if attr not in _data:
                if key:
                    abort(400,"%s missing required attribute %s" % (classname,
                        attr))
                obj[attr] = cls.get_attribute_default(attr)
            else:
                if not write and not _write_all:
                    abort(400, "%s write to %s not permitted" % (classname,
                        attr))

                # validate attribute
                obj[attr] = cls.validate_attribute(attr, _data[attr])

            if atype is str:
                if encrypt:
                    obj[attr] = aes_encrypt(obj[attr])
                    if obj[attr] is None:
                        abort(500, "%s encryption block failed for %s"%(
                            classname,attr))
                elif a.get("hash", False):
                    obj[attr] = hash_password(obj[attr])
                    if obj[attr] is None:
                        abort(500, "%s hash function failed for %s" % (
                            classname, attr))
            if key: keys[attr] = obj[attr]

        # check for any user provided attributes that do not exists
        for attr in _data:
            if attr not in cls._attributes:
                abort(400, "%s unknown attribute %s"%(classname, attr))
      
        # before anything (include before_create callback), if this node has a parent
        # dependency, check for the existence of the parent
        if cls._dependency is not None and cls._dependency.parent is not None and \
            cls._dependency.parent.obj is not None:
            # parent keys are always a subset of child keys, determine corresponding parent that
            # must exist for this child to be created
            parent = cls._dependency.parent.obj
            pkeys = {}
            for k in parent._keys:
                if k not in keys:
                    abort(500, "missing required parent key '%s'" % k)
                pkeys[k] = keys[k]
            p = parent.load(**pkeys)
            if not p.exists():
                okeys = []
                for attr in parent._attributes:
                    if parent._attributes[attr].get("key",False):
                        okeys.append("%s=%s" % (attr, obj.get(attr, "")))
                okeys = ",".join(okeys)
                abort(400, "parent (%s) does not exist" % okeys)


        # before create callback
        if callable(cls._access["before_create"]):
            try:
                new_obj = cls._access["before_create"](obj, **kwargs)
                assert new_obj is not None and isinstance(new_obj, dict)
                obj = new_obj
            except (BadRequest,NotFound) as e:
                cls.logger.debug("%s before create abort: %s" % (
                    classname, e))
                raise e
            except AssertionError as e:
                emsg = "invalid create object returned: %s"%str(type(new_obj))
                cls.logger.debug("%s before create callback assert: %s" % (
                    classname, emsg))
            except Exception as e:
                cls.logger.warn("%s before create callback failed: %s" % (
                    classname, e))
 
        # insert the update into the collection
        try:
            _id = cls.__mongo(collection.insert_one, obj)
            if hasattr(_id, "inserted_id") and cls._access["expose_id"]:
                ret_obj["_id"] = "%s" % _id.inserted_id
                kwargs["_id"] = ret_obj["_id"]
        except DuplicateKeyError as e:
            cls.logger.debug("%s duplicate entry %s" % (classname, e))
            # include keys in duplicate error message
            okeys = []
            for attr in cls._attributes:
                if cls._attributes[attr].get("key",False):
                    okeys.append("%s=%s" % (attr, obj.get(attr, "")))
            err = "%s duplicate entry " % classname
            if len(okeys)>0: err = "%s (%s)" % (err, ", ".join(okeys))
            abort(400, err)
        except PyMongoError as e:
            abort(500, "database error %s" % e)

        # after create callback
        if callable(cls._access["after_create"]):
            try:
                cls._access["after_create"](obj, **kwargs)
            except (BadRequest,NotFound) as e:
                cls.logger.debug("%s after create abort: %s" % (
                    classname, e))
                raise e
            except Exception as e:
                cls.logger.warn("%s after create callback failed: %s" % (
                    classname, e))

        # return object successfully inserted into database
        return ret_obj

    @classmethod
    def read(cls, _params={}, _filters=None, **kwargs):
        """ read rest object, aborts on error.
        
            support basic sorting, paging, and filtering via URL params
                page        : page to return (default: 0)
                page-size   : results per page (defaut: 1000)
                sort        : single attribute name in which to sort along with
                              optional pipe (|) and sort direction of 'asc'
                              or 'asc' with default of ascending. Multiple 
                              fields can be provided with commas. For example,
                              sort=classname|desc,node_id|asc
                count       : return just count of objects matching request
                filter      : add filter for attribute value with syntax:
                                filter=<expression>
                include     : comma separated list of attributes to include in 
                              each object. By default, all attributes are 
                              returned
            
            Return dict of with following attributes:
                count:      total number of objects matching query
                objects:    list of requested objects
        """
        cls.init()
        classname = cls._classname
        #cls.logger.debug("%s read request kwargs: %s"%(classname,kwargs))
        collection = get_db()[classname]

        # return attribute value independent of whether read is true or false
        _read_all = kwargs.get("__read_all", False)

        # calling function can override filter logic by provided _filters arg
        if _filters is None:
            # check kwargs for all possible keys.  If all keys are set then
            # set read_one to True which implies this was a direct read request
            read_one = True
            filters = {}
            for attr in cls._attributes:
                if cls._attributes[attr].get("key",False) and \
                    attr not in kwargs:
                    read_one = False
                if attr in kwargs:
                    filters[attr] = kwargs.get(attr, "")
            if cls._access["expose_id"]:
                # error on invalid id
                try:
                    if "_id" in kwargs: filters["_id"] = ObjectId(kwargs["_id"])
                    else: read_one = False
                except InvalidId as e:
                    abort(400, "%s._id invalid value '%s" % (
                        cls._classname,kwargs["_id"]))
            # additional read filters via user params
            filters = cls.filter(f=filters, params=_params)
        else: 
            read_one = False
            filters = _filters

        # set page and pagesize
        page = _params.get("page", 0)
        pagesize = _params.get("page-size", cls.DEFAULT_PAGE_SIZE)
        try: page = int(page)
        except Exception as e: abort(400, "invalid page value: %s" % page)
        try: pagesize = int(pagesize)
        except Exception as e: abort(400, "invalid pagesize: %s" % pagesize)

        if page < 0:
            abort(400, "page cannot be less than zero: %s" % page)
        if pagesize <= 0:
            abort(400, "page-size cannot be <= zero: %s" % pagesize)
        if pagesize > cls.MAX_PAGE_SIZE:
            abort(400,"page-size %s exceeds max: %s" % (
                pagesize,cls.MAX_PAGE_SIZE))
        if page*pagesize > cls.MAX_RESULT_SIZE:
            abort(400, "result size of page(%s)*page-size(%s) exceeds max %s"%(
                page, pagesize, cls.MAX_RESULT_SIZE))

        # before read callback
        if callable(cls._access["before_read"]):
            try:
                new_filters = cls._access["before_read"](filters, **kwargs)
                assert new_filters is not None and isinstance(new_filters, dict)
                filters = new_filters
            except (BadRequest,NotFound) as e:
                cls.logger.debug("%s before read abort: %s" % (
                    classname, e))
                raise e
            except AssertionError as e:
                emsg="invalid read filters returned: %s"%str(type(new_filters))
                cls.logger.warn("%s before create callback failed: %s" % (
                    classname, emsg))
            except Exception as e:
                cls.logger.warn("%s before read callback failed: %s" % (
                    classname, e))

        # add support for projects 
        projections = {}
        for i in _params.get("include","").split(","):
            if len(i)>0 and i not in projections: projections[i] = 1
        if len(projections)==0: projections = None

        # acquire cursor 
        try:
            cursor = cls.__mongo(collection.find, filters, projections)
        except PyMongoError as e:
            abort(500, "database error %s" % e)
            
        # check for sort options
        if "sort" in _params:
            sort = []
            reg="(?i)(?P<sort>[^|\,]+)(\|(?P<dir>[a-z]+))?(,|$)"
            for match in re.finditer(reg,_params["sort"].strip()):
                sdir= ASCENDING
                if match.group("dir") is not None:
                    _sdir = match.group("dir").lower()
                    if _sdir == "asc": pass
                    elif _sdir == "desc": sdir = DESCENDING
                    else:
                        em = "invalid sort direction (expected desc or asc) "
                        abort(400, "%s: %s for %s" %(em,_sdir,_params["sort"]))
                sort.append((match.group("sort"), sdir))
            if len(sort) == 0:
                abort(400, "invalid sort string: %s" % _params["sort"])
            # prepare cursor
            cursor = cls.__mongo(cursor.sort, sort) 
    
        # peform pagination
        cursor = cls.__mongo(cursor.skip, pagesize*page)
        cursor = cls.__mongo(cursor.limit, pagesize)

        # prepare return object
        ret = {
            "count": cls.__mongo(cursor.count),
            "objects": []
        }
        
        # only if user did not explicitly request count, iterate through results
        if "count" not in _params:
            for r in cursor:
                obj = {}
                for v in r:
                    if v in cls._attributes and (_read_all or \
                        cls._attributes[v].get("read",True)):
                        obj[v] = r[v]
                        if cls._attributes[v].get("type",str) is str and \
                            cls._attributes[v].get("encrypt",False):
                            obj[v] = aes_decrypt(obj[v])
                if cls._access["expose_id"] and "_id" in r:
                    obj["_id"] = "%s"%ObjectId(r["_id"])
                ret["objects"].append({cls._classname: obj})

        # perform 404 check for read_one scenario
        if read_one and ret["count"] == 0:
            # include keys in not-found error message
            okeys = []
            for attr in cls._attributes:
                if cls._attributes[attr].get("key",False):
                    okeys.append("%s=%s" % (attr, filters.get(attr, "")))
            if cls._access["expose_id"]:
                okeys.append("_id=%s" % filters.get("_id",""))
            err = "%s not found" % classname
            if len(okeys)>0: err = "%s (%s) not found" % (classname, 
                ", ".join(okeys))
            abort(404, err)

        # after read callback
        if callable(cls._access["after_read"]):
            try:
                new_ret = cls._access["after_read"](ret, **kwargs)
                assert new_ret is not None
                ret = new_ret
            except (BadRequest,NotFound) as e:
                cls.logger.debug("%s after read abort: %s" % (
                    classname, e))
                raise e
            except AssertionError as e:
                cls.logger.warn("%s after read callback failed: return None"%(
                    classname))
            except Exception as e:
                cls.logger.warn("%s after read callback failed: %s" % (
                    classname, e))

        # return read request
        return ret

    @classmethod
    def update(cls, _data={}, _params={}, _filters=None, **kwargs):
        """ update rest object, aborts on error.
        
            supports filter to limit objects updated IF update_bulk enabled
            under cls.META_ACCESS
                filter      : add filter for attribute value with syntax:
                                filter=<expression>

            support $patch attribute for json-patch with limited operations 
            ONLY for list attributes:
                "$patch": [{
                    "op": ["add", "remove"],
                    "path": "<path-string>"
                    "value": <value for add and replace>
                }]
                The path string is the attribute name. For nested objects uses
                mongo dotted syntax or json-patch syntax (since '/' and '.' are
                not supported for attribute names in this rest model). Ex:
                
                "$patch": [
                    {"op": "add", "value":5, "path":"list1"},
                    {"op": "remove", "path":"list1.5"},
                    {"op": "add", "value":8, "path":"dict1.list3.5.sublist1"},
                    {"op":" add", "value":9, "path":"dict1.list3.sublist1"},
                ]

                * add the value of 5 to the end of list1
                * remove the value at index 5 of list1
                * add the value 8 to the end of dict1.list3[index 5].sublist1
                * add the value 9 to the end of dict1.list3[all].sublist1

            Note, patch operations are performed sequentially on filtered 
            objects first and then any non-patch operation is applied. If 
            any part of patch operation fails then error is returned
            
            Return dict of with following attributes:
                success:    boolean success flag
                count:      total number of objects updated
        """
        cls.init()
        classname = cls._classname
        cls.logger.debug("%s update request kwargs: %s"%(classname,kwargs))
        collection = get_db()[classname]

        # allow write to attribute indepdent of whether write is true or false
        _write_all = kwargs.get("__write_all", False)

        # calling function can override filter logic by provided _filters arg
        if _filters is None:
            write_one = True
            filters = {}
            for attr in cls._attributes:
                if cls._attributes[attr].get("key",False) and \
                    attr not in kwargs:
                    write_one = False
                if attr in kwargs:
                    filters[attr] = kwargs.get(attr, "")
            if cls._access["expose_id"]:
                # error on invalid id
                try:
                    if "_id" in kwargs: filters["_id"]=ObjectId(kwargs["_id"])
                    else: write_one = False
                except InvalidId as e:
                    abort(400, "%s._id invalid value '%s" % (
                        cls._classname,kwargs["_id"]))
            # additional filters via user params
            if not write_one: 
                filters = cls.filter(f=filters, params=_params)
                # sanity check against bulk_update
                if not cls._access["bulk_update"]:
                    abort(400, "%s bulk update not enabled" % classname)
        else:
            filters = _filters
            write_one = False

        # build update object 
        obj = {}
        ret_obj = {"success": True, "count":0 }
        for attr in _data:
            if attr == "$patch":
                abort(400, "$patch not yet implemented")
            elif attr not in cls._attributes:
                abort(400, "%s unknown attribute %s"%(classname, attr))
            a = cls._attributes[attr]
            atype       = a.get("type", str)
            write       = a.get("write", True)
            key         = a.get("key", False)
            encrypt     = a.get("encrypt", False)
            # don't include keys in update object but allow user to provide them
            if key: continue
            if not write and not _write_all:
                abort(400, "%s write to %s not permitted" % (classname,attr))
            # validate attribute
            obj[attr] = cls.validate_attribute(attr, _data[attr])
            if atype is str:
                if encrypt:
                    obj[attr] = aes_encrypt(obj[attr])
                    if obj[attr] is None:
                        abort(500, "%s encryption block failed for %s"%(
                            classname,attr))
                elif a.get("hash", False):
                    obj[attr] = hash_password(obj[attr])
                    if obj[attr] is None:
                        abort(500, "%s hash function failed for %s" % (
                            classname, attr))

        # verify at least one value present in update
        if len(obj) == 0:
            abort(400, "at least one non-key attribute required for update")

        # before update callback
        if callable(cls._access["before_update"]):
            try:
                (nf, nd) = cls._access["before_update"](filters, obj, **kwargs)
                assert nf is not None and nd is not None
                assert isinstance(nf, dict) and isinstance(nd, dict)
                obj = nd
                filters = nf
            except (BadRequest,NotFound) as e:
                cls.logger.debug("%s before update abort: %s" % (
                    classname, e))
                raise e
            except AssertionError as e:
                emsg = "invalid update object returned: (%s, %s)" % (
                    str(type(nf)), str(type(nd)))
                cls.logger.info("%s before update callback assert: %s" % (
                    classname, emsg))
            except Exception as e:
                cls.logger.warn("%s before update callback failed: %s" % (
                    classname, e))
    
        # perform db update for selected objects
        try:
            r = cls.__mongo(collection.update_many, filters, {"$set":obj})
            ret_obj["count"] = r.matched_count
        except PyMongoError as e:
            abort(500, "database error %s" % e)

        # perform 404 check for write_one scenario
        if write_one and ret_obj["count"] == 0:
            # include keys in not-found error message
            okeys = []
            for attr in cls._attributes:
                if cls._attributes[attr].get("key",False):
                    okeys.append("%s=%s" % (attr, filters.get(attr, "")))
            if cls._access["expose_id"]:
                okeys.append("_id=%s" % filters.get("_id",""))
            err = "%s not found" % classname
            if len(okeys)>0: err = "%s (%s) not found" % (classname, 
                ", ".join(okeys))
            abort(404, err)

        # after update callback
        if callable(cls._access["after_update"]):
            try:
                cls._access["after_update"](filters, obj, **kwargs)
            except (BadRequest,NotFound) as e:
                cls.logger.debug("%s after update abort: %s" % (
                    classname, e))
                raise e
            except Exception as e:
                cls.logger.warn("%s after update callback failed: %s" % (
                    classname,e))

        # return object successfully database operation
        return ret_obj

    @classmethod
    def delete(cls, _params={}, _filters=None, **kwargs):
        """ delete rest object, aborts on error.
        
            supports filter to limit objects updated IF delete_bulk enabled
            under cls.META_ACCESS
                filter      : add filter for attribute value with syntax:
                                filter=<expression>

            implicitly delete all child objects if exists within RestDependency
            
            Return dict of with following attributes:
                success:    boolean success flag
                count:      total number of objects deleted
        """
        cls.init()
        classname = cls._classname
        cls.logger.debug("%s delete request filters:%s, kwargs: %s",classname,_filters,kwargs)
        collection = get_db()[classname]

        # calling function can override filter logic by provided _filters arg
        if _filters is None:
            write_one = True
            filters = {}
            for attr in cls._attributes:
                if cls._attributes[attr].get("key",False) and \
                    attr not in kwargs:
                    write_one = False
                if attr in kwargs:
                    filters[attr] = kwargs.get(attr, "")
            if cls._access["expose_id"]:
                # error on invalid id
                try:
                    if "_id" in kwargs: filters["_id"]=ObjectId(kwargs["_id"])
                    else: write_one = False
                except InvalidId as e:
                    abort(400, "%s._id invalid value '%s" % (
                        cls._classname,kwargs["_id"]))
            # additional filters via user params
            if not write_one: 
                filters = cls.filter(f=filters, params=_params)
                # sanity check against bulk_delete
                if not cls._access["bulk_delete"]:
                    abort(400, "%s bulk delete not enabled" % classname)
        else:
            filters = _filters
            write_one = False

        # before delete callback
        if callable(cls._access["before_delete"]):
            try:
                new_filters = cls._access["before_delete"](filters, **kwargs)
                assert new_filters is not None and isinstance(new_filters,dict)
                filters = new_filters
            except (BadRequest,NotFound) as e:
                cls.logger.debug("%s before delete abort: %s" % (
                    classname, e))
                raise e
            except AssertionError as e:
                emsg="invalid delete filter returned: %s"%str(type(new_filters))
                cls.logger.debug("%s before delete callback assert: %s" % (
                    classname, emsg))
            except Exception as e:
                cls.logger.warn("%s before delete callback failed: %s" % (
                    classname, e))

        # trigger delete on all child objects. This requires exact list of objects that match user
        # provided filter and limit that filter to appropriate keys only. This will require a read
        # operation to get list of delete objects followed by delete on corresponding children
        if cls._dependency is not None and len(cls._dependency.children)>0:
            matched_objs = cls.read(_filters=filters)
            for obj in matched_objs["objects"]:
                obj = obj[cls._classname]
                child_filters = {}
                for attr in obj:
                    if attr in cls._keys: child_filters[attr] = obj[attr]
                for n in cls._dependency.children:
                    if n.obj is not None:
                        cls.logger.debug("deleting child %s: %s", n.obj._classname, child_filters)
                        n.obj.delete(_filters=child_filters)


        # perform delete request
        ret_obj = {"success": True, "count":0 }

        # perform db update for selected objects
        try:
            r = cls.__mongo(collection.delete_many, filters)
            ret_obj["count"] = r.deleted_count
        except PyMongoError as e:
            abort(500, "database error %s" % e)

        # perform 404 check for write_one scenario
        if write_one and ret_obj["count"] == 0:
            # include keys in not-found error message
            okeys = []
            for attr in cls._attributes:
                if cls._attributes[attr].get("key",False):
                    okeys.append("%s=%s" % (attr, filters.get(attr, "")))
            if cls._access["expose_id"]:
                okeys.append("_id=%s" % filters.get("_id",""))
            err = "%s not found" % classname
            if len(okeys)>0: err = "%s (%s) not found" % (classname, 
                ", ".join(okeys))
            abort(404, err)

        # after delete callback
        if callable(cls._access["after_delete"]):
            try:
                cls._access["after_delete"](filters, **kwargs)
            except (BadRequest,NotFound) as e:
                cls.logger.debug("%s after delete abort: %s" % (
                    classname, e))
                raise e
            except Exception as e:
                cls.logger.warn("%s after delete callback failed: %s" % (
                    classname, e))

        # return object successfully database operation
        return ret_obj

    @classmethod
    def __mongo(cls, func, *args, **kwargs):
        """ perform mongo operation with retry """
        max_retries = 3
        retry_time = 3.0
        for i in xrange(0, max_retries):
            try:
                ts = time.time()
                return func(*args, **kwargs)
            except Exception as e:
                cls.logger.debug("traceback: %s" % traceback.format_exc())
                cls.logger.warn("database error: %s" % e)
                # some weird timeout bug on mongo connections - perform retry
                # if timeout in less than a few seconds (since this wasn't 
                # really a mongo timeout)
                if "timed out" in "%s"%e:
                    if time.time() - ts < 3:
                        cls.logger.debug("retrying operation in %s sec"%(
                            retry_time))
                        time.sleep(retry_time)
                        continue
            raise e
        cls.logger.warn("out of retries")
        raise e

# dummy class for testing
class Rest_Tests(Rest):
    META_ACCESS = {
        "bulk_read": True, 
        "bulk_update": True,
        "bulk_delete": True,
    }
    META = {
            "key": {"key": True, "type":str},
            "str": {"regex": "^[A-Z]{1,5}$"},
            "float": {"type":float, "min":0, "max":5},
            "bool": {"type": bool},
            "int": {"type":int},
            "list": {"type":list, "subtype":str},
            "dict": {
                "type": dict,
                "meta": {
                    "s1": {},
                    "i1": {"type": int},
                    "l1": {"type": list},
                    "l2": {"type": list, "subtype":dict, "meta":{
                        "ss1": {},
                        "ii1": {"type": int}
                    }},
                },
            },
            # list 2 is list of dict with only one attribute
            "list2": {
                "type": list,
                "subtype": dict,
                "meta": {
                    "s1": {},
                }                
            },
            # list 3 is list of dicts with no meta (so any dict is ok)
            "list3": {
                "type": list,
                "subtype": dict,
            },
    }
