
from ..utils import get_user_data
from .dependency import RestDependency
from flask import abort
from functools import wraps
from swagger.common import (swagger_create, swagger_read, swagger_update,
                            swagger_delete, swagger_generic_path)
import copy
import inspect
import re

root = RestDependency(None)
registered_classes = {}     # all register classes indexed by classname
registered_callbacks = {}   # all registered callbacks indexed by classname that needs to be attached
                            # to Rest classes

def api_register(path=None,  parent=None):
    """ register REST class with API.  Optional arguments are as follows: 

            path    custom api path relative to api blueprint. if not set then 
                    path is set to classname. I.e., if class is Bar in package
                    Foo, then classname is set to <api-blueprint>/foo/bar

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
    global root
    def decorator(cls):
        # stage for registration 
        _cname = cls.__name__.lower()
        if _cname not in registered_classes: 
            # create dependency node for class
            node = RestDependency(cls, path=path)
            if parent is None: root.add_child(node)
            else: 
                root.add_loose(node)
                node.set_parent_classname(parent)
            registered_classes[_cname] = cls
        return cls
    return decorator
   
def api_route(authenticated = True, keyed_url = False, methods = None, path = None, role = None, 
    summary = None, swag_args = None, swag_ret = None):
    """ register a custom route to a Rest class method. This simplifies route declaration and 
        validation under several common use cases below. Additionally, any non-key arguments
        provided under the function that are also defined under the META dict will use the 
        corresponding validators. 
            
            1) adding a route to a bound method
                class Foo(Rest):
                    ... META and META_ACCESS defined ...

                    @api_route(path="bar", methods=["POST"])
                    def bar(self, arg1):
                        # here the instance of Foo is provided already loaded from database based
                        # on keys within Foo.META.  If object was not found, then 404 would have 
                        # been returned by decorator. Also, all authentication and rbac is performed
                        # by the decorator
                        # Lastly, arg1 is pulled from post data and if not present a 400 error is 
                        # presented to the user. If arg1 is defined in Foo.META, then the validators
                        # will ensure the value is correct and casted with appropriate defaults.
                        
            2) adding a route to an unbound method
                class Foo(Rest):
                    ... META and META_ACCESS defined ...

                    @classmethod
                    @api_route(path="bar2", methods=["POST"], role=)
                    def bar2(cls, username, password):
                        # here the class method is executed without any db load.  The decorator 
                        # ensures the arguments username and password are within the post data and 
                        # aborts if not found.  Similar to the previous example, if these arguments
                        # are defined in Foo.META that the corresponding validators are executed to
                        # ensure username and password are valid values.
                        # Again, common authentication/rbac is performed
                
            3) adding a route without any validation
                class Foo(Rest):
                    ... META and META_ACCESS defined ...

                    @classmethod
                    @api_route(path="bar3", methods=["POST"], authenticated=False)
                    def bar3(cls):
                        # here authenticated is disabled so all POST are allowed. Also, there's no
                        # validation performed as this is a classmethod and no arguments defined. 
                        # To get user data, you can still use get_user_data and get_user_param 
                        data = get_user_data()
                        ...

        Arguments:
        authenticated   bool (default True), force user to be authenticated to access.  

        keyed_url   bool (default False), if true then path will include object keys before 
                    appending provided path. For example, 
                        Rest class foo with path /api/foo and key '<string:key1>' and a path 'bar'
                        requiring key in the url woudl result in one of the following:
                            a) if keyed_path is disabled under Rest META_ACCESS
                                '/api/foo/<string:key1>/bar'
                            b) if keyed_path is enabled under Rest META_ACCESS
                                '/api/foo/key1-<string:key1>/bar'

                    Note, if this decorator is added to class method with first argument of 'self'
                    and one or more keys exists or expose_id is enabled, then keyed_url is implied

        methods     list (default None), one or more methods that accept this route. If not provided
                    then will default to only GET method. Allowed values are GET, POST, PATCH, PUT, 
                    and DELETE.  OPTION is always allowed for CORS support.

        path        str, string url path with corresponding args required by endpoint function. 
                    This path is appended with the corresponding path to the Rest classname. For 
                    example,
                        Rest class foo with path /api/foo and path for new function bar with 
                        path='bar' would create '/api/foo/bar endpoint'

                    Extending on that example, if the endpoint requires a variable string var1, then
                    it can be included in the path 'bar/<string:var1>' which would create a final
                    endpoint: '/api/foo/bar/<string:var1>'

                    If no path is provided then function name is used as the path.

        role        str or int (default None), in addition to ensuring user is authenticated, an 
                    rbac role can also be enforced.  If provided value is an int within min/max 
                    Role, then that value will be used in rbac check.  The value can also be a string
                    (create_role, read_role, etc...) which will inherit the corresponding role
                    defined in META_ACCESS for this class.

        summary     swagger doc summary for route. If not provided, then function docstring will be
                    used.

        swag_args   list (default None), list of arguments to include in swag auto-documentation. 
                    This list is auto-created based on function arguments.  The behavior can be
                    overridden by passing an empty list (do not document any args) or custom list.
                    If the argument name exists in the Rest.META then corresponding validations will
                    be present in swagger docs. 

        swag_ret    list (default None), list of attributes in response to include in swag auto-
                    documentation.  Similiar to swag_args, if the attribute exists in the class META
                    then the corresponding documentation/validation will be present in swagger docs.
                    Note, there is no auto-detection for return values

    """
    route_info = RouteInfo(**{
        "authenticated": authenticated,
        "keyed_url": keyed_url,
        "methods": methods,
        "path": path,
        "role": role,
        "summary": summary,
        "swag_args": swag_args,
        "swag_ret": swag_ret
    })
    def add_route_decorator(func):
        spec = inspect.getargspec(func)
        if len(spec.args)>0:
            start_index = 1
            if spec.args[0]=="self": route_info.is_self = True
            elif spec.args[0]=="cls": route_info.is_cls = True
            else: start_index = 0
            route_info.args = [[i,_undefined()] for i in spec.args[start_index:] ]
            if spec.defaults is not None and len(spec.defaults)>0 and \
                    len(spec.defaults)<=len(route_info.args):
                    # walk backwords on spec.defaults to set corresponding args default
                    for i,v in enumerate(reversed(spec.defaults)):
                        route_info.args[-(i+1)][1] = v

            # set swag_args if not provided by the user
            if route_info.swag_args is None:
                route_info.swag_args = [a[0] for a in route_info.args]

        route_info.kwargs = (spec.keywords is not None)
        if route_info.path is None: route_info.path = func.__name__
        if route_info.summary is None: route_info.summary = ""
        route_info.function = func

        @wraps(func)
        def decorator(*args, **kwargs): return func(*args, **kwargs)
        decorator.route_info = route_info
        return decorator
    return add_route_decorator

def api_callback(callback, cls=None):
    """ register a function callback for a CRUD action for provided cls REST object. cls can be 
        omitted if provided function is a method of Rest class object.

        For each callback, the following keyword-arguments are provided.

            api         bool indicating initial request came from the REST api. This is used to 
                        distinguish between backend CRUD operations vs. user api CRUD actions

            cls         class instance of Rest object that is executing the callback

            data        dict that will be used in create or update.  Also, data can be final result
                        of read from db or final data object sent in create or update with auto
                        created attributes added (such as mongo _id for expose_id objects)

            filters     mongo syntax filter used in limit objects affected/return by read, update, 
                        or delete

            read_all    bool, backend request to read all attributes
                        
            write_all   bool, backend request to allow write to all attributes


        The following return value MAY be expected depending on the callback type:
            
            new_data    altered dict that should be sent to backend write OR returned to the user for
                        read requests

            new_filter  altered mongo syntax filter used to limit objects affected/returned by read,
                        update, or delete

        The supported callbacks are as follows:

            before_create   callback triggered before a create operation to the database. Function
                            can be used to alter the object data.
                                - expects return of new_data

            before_read     callback triggered before a read operation to the database. Function can
                            be used to alter the filter to limit/widen the read result.
                                - expects return of new_filter

            before_update   callback triggered before a update operation to the database. Function
                            can be used to alter the filter to limit/widen the scope of items 
                            affected by the update.  It can also alter the object data sent in the 
                            update request.
                                - expects return tuple (new_filter, new_data)

            before_delete   callback triggered before a delete operation to the database. Function
                            can be used to alter the filter to limit/widen the scope of items 
                            deleted.
                                - expects return of new_filter

            after_create    callback triggered after a successful db create.

            after_read      callback triggered after a db read. Function can be used to manipulate 
                            the return set to the user. The format of the returned request SHOULD
                            be the same as a normal api read request.
                                - expects return of new_data

            after_update    callback triggered after a db update.

            after_delete    callback triggered after a db delete
    """
    def add_callback_decorator(func):
        callback_info = CallbackInfo(callback=callback, function=func)
        # if cls is provided, then ensure it inherits rest (basic check) and then add to 
        # registered_callbacks. Else, assume callback is tied to cls that will be caught at register
        if cls is not None:
            cls_name = "%s" % cls   # this includes full package path for name
            if not hasattr(cls, "META") or not hasattr(cls, "_access") \
                or not hasattr(cls, "_classname"):
                raise Exception("cls %s has not inherited Rest class" % cls_name)
            if cls_name not in registered_callbacks: 
                registered_callbacks[cls_name] = {"cls": cls}
            registered_callbacks[cls_name][callback] = callback_info

        @wraps(func)
        def decorator(*args, **kwargs): return func(*args, **kwargs)
        decorator.callback_info = callback_info
        return decorator
    return add_callback_decorator

def register(api, uni=True):
    """ register routes for each class with provided api blueprint and build per-object swagger 
        definition
    """
    # first handle object dependencies sitting in RestDependency root
    global root
    root.build()
    if uni:
        # if uni is enabled then required before any other object is created
        from .universe import Universe
        uni_node = root.find_classname("universe")
        children = [c for c in root.children]
        for c in children:
            if c is uni_node: continue
            root.remove_child(c)
            uni_node.add_child(c)
            c.set_parent_classname("universe")
        root = uni_node

    # raise warning for keypath collision (indexed per method)
    unique_path = {}
    def warn_dup(c, method, path):
        if type(method) is not list: method = [method]
        for m in method:
            if m not in unique_path: unique_path[m] = {}
            if path in unique_path[m]:
                c.logger.warn("duplicate path %s to %s (%s)", c._classname, unique_path[m][path],
                    path)
            else:
                unique_path[m][path] = c._classname

    for node in root.get_ordered_objects():
        c = node.obj
        #c.logger.debug("*"*80)
        c._dependency = node
        c.init(force=True)
        # after class has been init, check for method route_info and callback_info
        for name, method in c.__dict__.iteritems():
            # route_info for normal bound methods on object
            if hasattr(method, "route_info"): 
                c._access["routes"].append(method.route_info)
            # route_info for classmethod and staticmethods
            elif hasattr(method, "__func__") and hasattr(method.__func__, "route_info"):
                c._access["routes"].append(method.__func__.route_info)

            # callback_info for normal bound methods on object
            if hasattr(method, "callback_info"): 
                c._access[method.callback_info.callback] = method.callback_info
            # callback_info for classmethod and staticmethods
            elif hasattr(method, "__func__") and hasattr(method.__func__, "callback_info"):
                c._access[method.__func__.callback_info.callback] = method.__func__.callback_info

        # update parent dependency
        parent = None
        if node.parent is not None and node.parent.obj is not None:
            parent = node.parent.obj
            #c.logger.debug("parent: %s" , parent._classname)
        keys = {}   # dict of keys per key_index
        for attr in c._attributes:
            if c._attributes[attr]["key"] and (parent is None or \
                (parent is not None and attr not in parent._keys)):
                _type = c._attributes[attr]["type"]
                _index = c._attributes[attr]["key_index"]
                if _index not in keys: keys[_index] = {}
                key_type = c._attributes[attr]["key_type"]
                if key_type in ["string","int","float","path","any","uuid", "filename"]:
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
            for attr in sorted(keys[_index]):
                c._dn_attributes.append(attr)
                key_string.append(keys[_index][attr])
        key_string = "/".join(key_string)

        # create CRUD rules with default paths
        # create key path and swagger key paths
        path = "/%s" % "/".join(c._classname.split("."))
        if parent is None:
            if len(key_string)>0:
                key_path = "%s/%s" % (path, key_string)
            else:
                key_path = path
        else:
            # add namespace if present
            if c._access["namespace"] is not None and len(c._access["namespace"])>0:
                key_path = "%s/%s/%s"%(parent._key_path, c._access["namespace"].lower(),key_string)
            else:
                key_path = "%s/%s" % (parent._key_path, key_string)
            c._dn_attributes = parent._dn_attributes + c._dn_attributes
        # remove duplicate slashes from all paths
        path = re.sub("//","/", path)
        key_path = re.sub("//","/", key_path)
        key_swag_path = re.sub("<[a-z]+:([^>]+)>",r"{\1}", key_path)
        c._swagger = {}

        # add create path
        if c._access["create"]:
            endpoint = "%s_create" % c.__name__.lower()
            api.add_url_rule(path, endpoint , c.api_create, methods=["POST"])
            #c.logger.debug("registered create path: POST %s", path)
            if path not in c._swagger: c._swagger[path] = {}
            swagger_create(c, path)

        # create path will not have _id but read, update, and delete will 
        # include _id as key (if enabled)
        if c._access["expose_id"]: 
            # if keyed_path is enabled OR there is parent present ,then we should use
            # /_classname-{_id} for the _id key
            # else, the key_path will already include the classname and we should just use /{_id}
            if parent is not None or c._access["keyed_path"]:
                cname = re.sub("\.","/", c._classname)
                key_path = re.sub("//", "/", "%s/%s-%s" % (key_path, cname, "<string:_id>"))
            else:
                key_path = re.sub("//", "/", "%s/%s" % (key_path, "<string:_id>"))
            key_swag_path = re.sub("<[a-z]+:([^>]+)>",r"{\1}", key_path)
            c._dn_attributes.append("_id")
           
        # set final _key_path and _key_swag_path along with calculated _dn_path
        c._key_path = key_path
        c._key_swag_path = key_swag_path
        c._dn_path = re.sub("{.+?}","{}", c._key_swag_path)

        #c.logger.debug("%s, dn: %s, attributes: %s", c._classname, c._dn_path, c._dn_attributes)
        keyed = lambda cls: (key_path is not None and len(cls._keys)>0 or c._access["expose_id"])
        bulk = lambda cls: (key_path!=path or (len(cls._keys)==0 and not cls._access["expose_id"]))

        # add read paths
        if c._access["read"]:
            if keyed(c):
                endpoint = "%s_read" % c.__name__.lower()
                api.add_url_rule(key_path, endpoint, c.api_read,methods=["GET"])
                #c.logger.debug("registered read path: GET %s", key_path)
                swagger_read(c, key_swag_path, bulk=False)
                warn_dup(c, "GET", key_path)

            if c._access["bulk_read"] and bulk(c):
                endpoint = "%s_bulk_read" % c.__name__.lower()
                api.add_url_rule(path, endpoint, c.api_read, methods=["GET"])
                #c.logger.debug("registered bulk read path: GET %s", path)
                swagger_read(c, path, bulk=True)
                warn_dup(c, "GET", path)

        # add update paths
        if c._access["update"]:
            if keyed(c):
                endpoint = "%s_update" % c.__name__.lower()
                api.add_url_rule(key_path,endpoint,c.api_update,
                    methods=["PATCH","PUT"])
                #c.logger.debug("registered update path: PATCH,PUT %s", key_path)
                swagger_update(c, key_swag_path, bulk=False)
                warn_dup(c, ["PUT", "PATCH"], key_path)

            if c._access["bulk_update"] and bulk(c):
                endpoint = "%s_bulk_update" % c.__name__.lower()
                api.add_url_rule(path,endpoint,c.api_update,
                    methods=["PATCH","PUT"])
                #c.logger.debug("registered bulk update path: PATCH,PUT %s",path)
                swagger_update(c, path, bulk=True)
                warn_dup(c, ["PUT", "PATCH"], path)

        # add delete paths
        if c._access["delete"]:
            if keyed(c):
                endpoint = "%s_delete" % c.__name__.lower()
                api.add_url_rule(key_path,endpoint,c.api_delete,
                    methods=["DELETE"])
                #c.logger.debug("registered delete path: DELETE %s", key_path)
                swagger_delete(c, key_swag_path, bulk=False)
                warn_dup(c, "DELETE", key_path)

            if c._access["bulk_delete"] and bulk(c):
                endpoint = "%s_bulk_delete" % c.__name__.lower()
                api.add_url_rule(path,endpoint,c.api_delete,methods=["DELETE"])
                #c.logger.debug("registered bulk delete path: DELETE %s", path)
                swagger_delete(c, path, bulk=True)
                warn_dup(c, "DELETE", path)

        # handle custom routes
        for r in c._access["routes"]:
            # build dynamic route function to handle rbac/role (and any new pre_check features)
            r.init_function(c)
            if not callable(r.function):
                #c.logger.warn("%s skipping invalid route: %s, bad function",c._classname,r.function)
                continue
            if len(r.path) == 0:
                #c.logger.warn("%s skipping invalid route: %s, bad path", c._classname, r.path)
                continue
            if r.keyed_url:
                rpath = "%s/%s"%(key_path, re.sub("(^/+)|(/+$)","",r.path))
            else: 
                rpath = "%s/%s"%(path, re.sub("(^/+)|(/+$)","",r.path))
        
            rpath = re.sub("//","/", rpath)
            endpoint="%s_%s" % (c.__name__.lower(), r.function.__name__)
            
            api.add_url_rule(rpath, endpoint, r.function, methods=r.methods)
            c.logger.debug("registered custom path: %s %s", r.methods, rpath)
            swag_rpath = re.sub("<[a-z]+:([^>]+)>",r"{\1}", rpath)
            swagger_generic_path(c, swag_rpath, r.methods[0], r.summary, r.swag_args, r.swag_ret,
                    authenticated=r.authenticated, role=r.role)
            warn_dup(c,r.methods,rpath)

    # check registered_callbacks for additional callback_info (decorators used outside of class)
    # and set the method to the registered CallbackInfo object
    for cls_name in registered_callbacks:
        cb = registered_callbacks[cls_name]
        cls = cb["cls"]
        for method in cb:
            if method == "cls": continue
            cls._access[method] = cb[method]

    # need to loop through all rest objects again and init callbacks
    for node in root.get_ordered_objects():
        c = node.obj
        c.init_callbacks()

class _undefined(): 
    """ local class type for differentiating between None and never defined """
    pass

class RouteInfo(object):
    """ maintain standard route info attributes.  The attributes maintained within this class are 
        as follows:
    
        authenticated   bool, see authenticated under Rest decorator api_route

        keyed_url       bool, see keyed_url under Rest decorator api_route   

        function        func, function to accept route

        methods         list(str).  See methods under Rest decorator api_route

        path            str, see path under Rest decorator api_route

        role            int or str, see role under Rest decorator api_route

        summary         str. See summary under Rest decorator api_route

        swag_args       list(str).  See swag_args under Rest decorator api_route

        swag_ret        list(str).  See swag_ret under Rest decorator api_route
    
    """
    # allowed string roles
    allowed_roles = [
        "create_role",
        "read_role",
        "update_role",
        "delete_role",
        "default_role",
    ]
    def __init__(self, **kwargs):
        self.authenticated = kwargs.get("authenticated", True)
        self.keyed_url = kwargs.get("keyed_url", False)
        self.methods = kwargs.get("methods", None)
        self.path = kwargs.get("path", None)
        self.role = kwargs.get("role", None)
        self.summary = kwargs.get("summary", None)
        self.swag_args = kwargs.get("swag_args", None)
        self.swag_ret = kwargs.get("swag_ret", None)
        self.function = kwargs.get("function", None)
        # dynamically discovered by api_route decorator
        self.is_self = False    # for bound functions with first argument 'self'
        self.is_cls = False     # for classmethod functions with first argument 'cls'
        self.args = []          # list of function args lists[name, default], excluding self/cls
        self.kwargs = False     # bool indicating whether function expects keyword args
        # flag indicate function init has completed
        self.init = False       
        self.ofunc = None   

    def init_function(self, cls):
        """ wrap function with route prechecks """
        if self.init: return

        # prevent duplicate inits
        self.init = True

        # don't do anything if original function is not callable
        if not callable(self.function): return

        # override keyed_url to true if a key exists and normal class method used decorator
        if self.is_self and not self.keyed_url:
            if cls._access["expose_id"]: self.keyed_url = True
            elif len(cls._attributes)>0:
                for attr in cls._attributes:
                    if cls._attributes[attr]["key"]: 
                        self.keyed_url = True
                        break

        # force role to a valid value
        if isinstance(self.role, basestring) and self.role in RouteInfo.allowed_role:
            self.role = cls._access[self.role]
        elif not isinstance(self.role, int):
            self.role = cls._access["default_role"]

        # set ptr of ofunc to original function
        self.ofunc = self.function

        def pre_checks(**kwargs):
            """ perform common prechecks/db loads before triggering method """
            # authentication/rbac checks first
            if self.authenticated:
                # rbac always performs authentication check so can just trigger rbac if role is set
                if self.role is not None:
                    if type(self.role) is int:
                        cls.rbac(role=self.role)
                    else:
                        cls.rbac(action=self.role)
                else:
                    # no parameters will trigger rbac to check default_role defined under class
                    cls.rbac()
            # if keyed url then need to build list of arguments used for initializing class object or 
            # for provding as initial arguments to function
            keys = {}
            ordered_keys = []
            if self.keyed_url:
                # dn_attributes is ordered list of key attributes that calling function will expect
                for attr in cls._dn_attributes:
                    if attr in kwargs:
                        ordered_keys.append(kwargs[attr])
                        keys[attr] = kwargs[attr]
            # validate non-key arguments from request data (independent of method here although we 
            # don't expect user data in a GET request)
            ordered_args = []
            optional_args = {}
            data = get_user_data()
            for (farg, fval) in self.args:
                # skip key args if keyed_url is set
                if self.keyed_url and farg in keys: continue
                required = isinstance(fval, _undefined)
                if farg in data:
                    # perform validation if attribute exists in _attributes or _attributes_reference
                    val = data[farg]
                    if farg in cls._attributes or farg in cls._attributes_reference:
                        val = cls.validate_attribute(farg, data[farg])
                    # add to ordered args if required, else add to optional_args.
                    if required: ordered_args.append(val)
                    else: optional_args[farg] = val
                elif required:
                    abort(400,"missing required attribute %s" % farg)

            # prepare final list of arguments for function
            if self.is_self:
                # for self-bound methods, load mo add add as first argument to ordered_args
                mo = cls.load(**keys)
                if not mo.exists(): 
                    okeys = ",".join(["%s=%s" % (k,keys[k]) for k in keys])
                    abort(404, "%s (%s) not found" % (cls._classname, okeys))
                ordered_args.insert(0, mo)
            else:
                ordered_args = ordered_keys + ordered_args
                # for class method, first argument is cls
                if self.is_cls: ordered_args.insert(0, cls)
            # execute the function
            if len(optional_args)>0:
                return self.ofunc(*ordered_args, **optional_args)
            else:
                return self.ofunc(*ordered_args)

        # remapping the function to prechecks function
        pre_checks.__doc__ = self.ofunc.__doc__
        pre_checks.__name__ = self.ofunc.__name__
        self.function = pre_checks

        # set summary to provided summary or function doc string
        if self.summary is None or len(self.summary) == 0: 
            self.summary = self.function.__doc__

        # set methods to a valid value, with default of GET
        methods = []
        if isinstance(self.methods, list):
            for m in self.methods:
                if m not in ["GET","DELETE","POST","PATCH","PUT"]:
                    #cls.logger.warn("%s invalid method: (%s) %s", cls._classname, self, m)
                    continue
                if m not in methods: methods.append(m)
        if len(methods)==0:
            #cls.logger.warn("%s no valid methods %s", cls._classname, r)
            methods=["GET"]
        self.methods = methods

        return self


class CallbackInfo(object):
    """ maintain standard callback info attributes.  The attributes maintained within this class are 
        as follows:
            function    func, function to accept callback

            method      str, see method in Rest api_callback for allowed types and further info
    """
    allowed_args = [
        "api", 
        "cls", 
        "data", 
        "filters", 
        "read_all", 
        "write_all"
    ]
    allowed_callbacks = [
        "before_create", 
        "before_read", 
        "before_update", 
        "before_delete",
        "after_create", 
        "after_read", 
        "after_update", 
        "after_delete"
    ]
    def __init__(self, callback=None, function=None):
        if not isinstance(callback, basestring) or callback not in CallbackInfo.allowed_callbacks:
            raise Exception("invalid callback type: %s" % callback)
        if function is None or not callable(function):
            raise Exception("invalid function(%s) for callback %s" % (function, callback))
        self.callback = callback
        self.function = function
        self.is_self = False
        self.is_cls = False
        self.kwargs = False
        self.arg_list = []
        self.ofunc = None

    def init_function(self, cls):
        # init function with provided Rest class
        # we will support function accepting arg with same name as callback kwargs keys, just kwargs
        # dict, or mix. Only the args function requests will be provided.  If an unsupported arg is
        # present then an exception is raised
        spec = inspect.getargspec(self.function)
        self.kwargs = (spec.keywords is not None)
        if len(spec.args)>0:
            start_index = 1
            if spec.args[0]=="cls": self.is_cls = True
            elif spec.args[0]=="self": self.is_self = True
            else: start_index = 0
            for i, a in enumerate(spec.args[start_index:]):
                if a == "cls" and self.cls:
                    raise Exception("duplicate callback argument '%s' in %s" % (a, self.function.__name__))
                if a in self.arg_list:
                    raise Exception("duplicate callback argument '%s' in %s" % (a, self.function.__name__))
                if a not in CallbackInfo.allowed_args:
                    raise Exception("unsupported callback argument '%s' in %s, expecting %s" % (a, 
                        self.function.__name__, CallbackInfo.allowed_args))
                self.arg_list.append(a)

        # remap ofunc to original function
        self.ofunc = self.function

        # build new function that will send only required args to callback
        def decorator(**kwargs):
            args = [kwargs.get(a, None) for a in self.arg_list] 
            copy_kwargs = copy.deepcopy(kwargs)
            for a in self.arg_list:
                if a in copy_kwargs: 
                    copy_kwargs.pop(a, None)

            # instaniated object is best effort... It does not make since for callbacks
            if self.is_self:
                if self.kwargs: return self.ofunc(cls(), *args, **copy_kwargs)
                else: return self.ofunc(cls(), *args)
            elif self.is_cls:
                if self.kwargs: return self.ofunc(cls, *args, **copy_kwargs)
                else: return self.ofunc(cls, *args)
            else:
                if self.kwargs: return self.ofunc(*args, **copy_kwargs)
                else: return self.ofunc(*args)

        # remap function to the decorator
        self.function = decorator

