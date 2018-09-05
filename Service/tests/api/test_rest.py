"""
test generic rest object implementation
"""
from werkzeug.exceptions import (NotFound, BadRequest)
from app.models.rest import (Rest, api_register)
import logging, json
import pytest

# module level logging
logger = logging.getLogger(__name__)

rest_url = "/api/test/rest"
rest_url_key = "/api/uni/key-{}" 
rest_classname = "test.rest"
good_request = 200
bad_request = 400
not_found = 404


# Test class regisetered with API
@api_register(path="test/rest")
class Rest_TestClass(Rest):
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
            "hash": {
                "type": str,
                "hash": True,
                "default": "abcd",
                "description": "general attribute that can be 'hashed'"
            },
            "encrypt": {
                "type": str,
                "encrypt": True,
                "description": "general attribute that can be encrypted and decrypted"
            }
    }


# Test class regisetered with API
@api_register(path="test/secure")
class Rest_Secure(Rest):
    META_ACCESS = {
        "bulk_read": True,
        "bulk_update": True,
        "bulk_delete": True,
    }
    META = {
            "key": {"key": True, "type":str},
            "hash": {
                "type": str,
                "hash": True,
                "read": False,
                "default": "abcd",
                "description": "general attribute that can be 'hashed'"
            },
            "encrypt": {
                "type": str,
                "encrypt": True,
                "description": "general attribute that can be encrypted and decrypted"
            }
    }


def pretty_print(js):
    """ try to convert json to pretty-print format """
    try:
        return json.dumps(js, indent=4, separators=(",", ":"))
    except Exception as e:
        return "%s" % js

def get_test_object(meta, return_instance = True):
    # provide meta data and return instance of Rest class implementing meta
    class Dynamic_Test(Rest):
        META = meta
        META_ACCESS = {}
    if return_instance: return Dynamic_Test()
    else: return Dynamic_Test

def assert_bad_request(fn, *args, **kwargs):
    try:
        r = fn(*args, **kwargs)
        raise Exception("expected BadRequest but received: %s" % r)
    except BadRequest as e: 
        logger.debug("BadRequest: %s", e)

def assert_not_found(fn, *args, **kwargs):
    try:
        r = fn(*args, **kwargs)
        raise Exception("expecte NotFound but received: %s" % r)
    except NotFound as e: 
        logger.debug("NotFound: %s", e)

@pytest.fixture(scope="function")
def rest_cleanup(request, app):
    # drop test.rest (objects for Rest_TestClass) and dnyamic.test for Dynamic_Test objects
    def teardown():
        db = app.db
        db.test.rest.drop()
        db.test.secure.drop()
        db.dynamic.test.drop()
    request.addfinalizer(teardown)
    return

def test_rest_validate_attribute_basic():
    # verify basic attributes (float, int, str, bool)  are casted correctly 
    t = get_test_object({
        "str": {"type": str, "default": "string"},
        "float": {"type": float, "default":1.0 },
        "int": {"type": int, "default": 1},
        "bool": {"type": bool, "default": True},
    })

    assert t.validate_attribute("str", None) == "None"
    assert t.validate_attribute("str", {}) == "{}"
    assert t.validate_attribute("str", 1) == "1"
    assert t.validate_attribute("str", "string") == "string"

    assert t.validate_attribute("float", 2.0) == 2.0 
    assert t.validate_attribute("float", "3.0") == 3.0
    assert_bad_request(t.validate_attribute,"float", None)
    
    assert t.validate_attribute("int", 4) == 4
    assert t.validate_attribute("int", "5") == 5
    assert t.validate_attribute("int", -2) == -2
    assert t.validate_attribute("int", "-2") == -2
    assert_bad_request(t.validate_attribute, "int", "s")
    assert_bad_request(t.validate_attribute, "int", None)

    assert t.validate_attribute("bool", True) is True
    assert t.validate_attribute("bool", False) is False
    assert t.validate_attribute("bool", "true") is True
    assert t.validate_attribute("bool", "false") is False
    assert t.validate_attribute("bool", "True") is True
    assert t.validate_attribute("bool", "False") is False
    assert t.validate_attribute("bool", 0) is False
    assert t.validate_attribute("bool", 1) is True
    assert_bad_request(t.validate_attribute, "bool", None)
    assert_bad_request(t.validate_attribute, "bool", -1)
    assert_bad_request(t.validate_attribute, "bool", 2)
    assert_bad_request(t.validate_attribute, "bool", "t")


def test_rest_validate_attribute_regex():
    # ensure regex is correctly applied and BadRequest raised for invalid value
    t = get_test_object({
        "str": {"type": str, "default": "string", "regex":"^[a-zA-Z]{5,10}$"},
    })
    assert t.validate_attribute("str", "abcdE") == "abcdE"
    assert t.validate_attribute("str", "abcdEfghi") == "abcdEfghi"
    assert_bad_request(t.validate_attribute, "str", "a")
    assert_bad_request(t.validate_attribute, "str", "1")
    assert_bad_request(t.validate_attribute, "str", "abcdefghijkl")

def test_rest_validate_attribute_formatter():
    # ensure formatter is applied correctly
    def lower(v): return v.lower()
    def absolute(v): return abs(v)
    t = get_test_object({
        "str": {"type": str, "formatter":lower},
        "int": {"type": int, "formatter":absolute},
    })
    assert t.validate_attribute("str", "ABCD") == "abcd"
    assert t.validate_attribute("int", -23) == 23

def test_rest_validate_attribute_min_max():
    # ensure min/max are correctly applied and BadRequest raised for invalid 
    # value
    t = get_test_object({
        "int": {"type": int, "min":5, "max": 10},
    })
    assert t.validate_attribute("int", 5) == 5
    assert t.validate_attribute("int", 7) == 7
    assert t.validate_attribute("int", 10) == 10
    assert_bad_request(t.validate_attribute, "int", 4)
    assert_bad_request(t.validate_attribute, "int", 11)

def test_rest_validate_attribute_values():
    # ensure 'values' selection is applied and BadRequest raised for invalid
    # value
    t = get_test_object({
        "str": {"type": str, "values": ["abcd", "1999", "2005"] },
    })
    assert t.validate_attribute("str", "abcd") == "abcd"
    assert t.validate_attribute("str", 1999) == "1999"
    assert_bad_request(t.validate_attribute, "str", "A")

def test_rest_validate_attribute_list_with_values_validator():
    # ensure an attribute of type list with a values validator correctly
    # validates each value within the list
    t = get_test_object({
        "list": {"type":list, "subtype":str, "values":["abcd","1999","2005"]}
    })
    assert t.validate_attribute("list", ["abcd"]) == ["abcd"]
    assert t.validate_attribute("list", ["1999","2005"]) == ["1999","2005"]
    assert t.validate_attribute("list", ["2005"]) == ["2005"]
    assert_bad_request(t.validate_attribute, "list", "abcd")
    assert_bad_request(t.validate_attribute, "list", "1999")
    assert_bad_request(t.validate_attribute, "list", ["abcd", "1"])
    assert_bad_request(t.validate_attribute, "list", [["abcd"]])

def test_rest_validate_attribute_list_subtype_basic():
    # ensure for basic list attribute, subtype is applied for basic types (int,
    # float, str, bool) and are casted correctly
    t = get_test_object({
        "lstr": {"type": list, "subtype": str},
        "lfloat": {"type": list, "subtype": float},
        "lint": {"type": list, "subtype": int},
        "lbool": {"type": list, "subtype": bool},
    })
    assert t.validate_attribute("lstr", ["a", 1, 2]) == ["a", "1", "2"]
    assert_bad_request(t.validate_attribute, "lstr", "a")
   
    assert t.validate_attribute("lfloat", [1,2,"3.5",4]) == [1,2,3.5,4]
    assert t.validate_attribute("lint", ["0",1,2,"3"]) == [0,1,2,3]
    assert t.validate_attribute("lbool", [True, False, "true", 0]) == \
                                         [True, False, True,   False]
    assert t.validate_attribute("lint", []) == []

    assert_bad_request(t.validate_attribute, "lfloat", [1.0, "a"])
    assert_bad_request(t.validate_attribute, "lint", [1, "a"])
    assert_bad_request(t.validate_attribute, "lbool", ["a", True])

def test_rest_validate_attribute_dict():
    # ensure for dict attribute, each subtype is captured and min/max/regex/
    # and values filters are correctly applied.  Also, ensure that defaults are
    # applied for missing values.
    t = get_test_object({
        "dict": {
            "type": dict,
            "meta": {
                "str": {"type": str, "default":"s1", "regex": "^[a-z1-5]+$"},
                "bool": {"type": bool, "default":False},
                "int": {"type": int, "default":5, "min":1, "max":10},
                "dict2": {
                    "type": dict,
                    "meta": {
                        "str2": {"type": str, "default": "s2"},
                    }
                } 
            }
        }
    })

    r = t.validate_attribute("dict", {})
    assert "str" in r and r["str"] == "s1"
    assert "bool" in r and r["bool"] is False
    assert "int" in r and r["int"] == 5
    assert "dict2" in r and r["dict2"]["str2"] == "s2"

    r = t.validate_attribute("dict", {
        "str": "aa",
        "bool": True,
        "int": 6,
        "dict2": {
            "str2": "s3"
        }
    })
    assert "str" in r and r["str"] == "aa"
    assert "bool" in r and r["bool"] is True
    assert "int" in r and r["int"] == 6
    assert "dict2" in r and r["dict2"]["str2"] == "s3"

    # invalid values should fail regex or type
    assert_bad_request(t.validate_attribute, "dict", {"str": "a6"})
    assert_bad_request(t.validate_attribute, "dict", {"bool": "b"})
    assert_bad_request(t.validate_attribute, "dict", {"int": 13})
    # ensure unknown attribute in dict raises an error
    assert_bad_request(t.validate_attribute, "dict", {"unknown":1})

def test_rest_validate_attribute_list_of_dict():
    # ensure subtype of 'dict' for list works as expected
    t = get_test_object({
        "list": {
            "type": list,
            "subtype": dict,
            "meta": {
                "str": {"type": str, "default":"s1", "regex": "^[a-z1-5]+$"},
                "bool": {"type": bool, "default":False},
                "int": {"type": int, "default":5, "min":1, "max":10},
                "dict2": {
                    "type": dict,
                    "meta": {
                        "str2": {"type": str, "default": "s2"},
                    }
                } 
            }
        }
    })
    
    assert_bad_request(t.validate_attribute, "list", {})
    assert t.validate_attribute("list", []) == []
    
    r = t.validate_attribute("list", [{}, {}])
    assert len(r) == 2
    assert r[0]["str"] == "s1" and r[1]["str"] == "s1"

    r = t.validate_attribute("list", [{}, {
        "str": "s2",
        "dict2": {
            "str2": "s3"
        }
    }])
    assert len(r) == 2
    assert r[0]["str"] == "s1" and r[0]["dict2"]["str2"] == "s2"
    assert r[1]["str"] == "s2" and r[1]["dict2"]["str2"] == "s3"

    assert_bad_request(t.validate_attribute, "list", [{}, {"str": "s6"}])

def test_rest_validate_attribute_list_of_list():
    # verify list of list are correctly validated
    t = get_test_object({
        "list": {
            "type": list,
            "subtype": list,
        }
    })

    r = t.validate_attribute("list", [[0,1,2,3], [4,5,6,7]])
    assert len(r) == 2
    assert len(r[0]) == 4
    assert len(r[1]) == 4

def test_rest_validate_attribute_dict_of_list_of_dicts():
    # verify dict with list meta that contains list of dicts works
    t = get_test_object({
        "dict": {
            "type": dict,
            "meta": {
                "list0": {"type": list, "subtype": int},
                "list": { "type": list, "subtype": dict, "meta": {
                    "substr": {
                        "type": str, 
                        "default": "string", 
                        "regex":"^[a-z]+$"
                    }
                }},
            },
        }
    })

    assert t.validate_attribute("dict", {}) == {"list":[], "list0":[]}
    r = t.validate_attribute("dict", {
        "list": [{}, {}, {"substr":"str"}]
    })
    assert len(r["list"]) == 3
    assert r["list"][0]["substr"] == "string"
    assert r["list"][1]["substr"] == "string"
    assert r["list"][2]["substr"] == "str"
    assert_bad_request(t.validate_attribute, "dict", {
        "list":[{"substr":"str1"}]})

def test_rest_validate_attribute_list_of_dict_no_meta():
    # verify that list of dicts with no meta defined allows any dict
    t = get_test_object({
        "list": {
            "type": list,
            "subtype": dict
        }
    })
    assert t.validate_attribute("list", [{"a1":1}]) == [{"a1":1}]

def test_rest_filter():
    # verify expected mongo filters based on provided logic strings
    t = get_test_object({
        "str": {"type":str },
        "int": {"type": int },
        "float": {"type": float },
        "bool": {"type": bool },
        "flatlist": {"type": list, "subtype": str},
        "dict": {"type": dict, "meta": {
            "substr": {"type": str},
            "sublist": {"type": list, "subtype": int},
            "subdict": {"type": dict, "meta": {
                "sstr": {"type": str},
                "sint": {"type": int},
            }},
        }},
        "list": {"type": list, "subtype": dict, "meta": {
            "substr": {"type": str},
            "sublist": {"type": list, "subtype": int},
            "subdict": {"type": dict, "meta": {
                "sstr": {"type": str},
                "sint": {"type": int},
            }},
        }},
    })
  
    filters = {
        # key: expected result

        # simple filter cases
        "eq(\"str\",\"s1\")":   {"str": "s1"},
        "eq(\"str\", \"s1\\\"123\")": {"str": "s1\\\"123"},
        "eq(\"str\", \"s1'123\")":  {"str": "s1'123"},
        "neq(\"str\",\"s1\")": {"str": {"$ne": "s1"}},
        "gt(\"str\",\"s1\")": {"str": {"$gt": "s1"}},
        "ge(\"str\",\"s1\")": {"str": {"$gte": "s1"}},
        "lt(\"str\", \"s1\")": {"str": {"$lt": "s1"}},
        "le(\"str\", \"s1\")": {"str": {"$lte": "s1"}},
        "regex(\"str\", \"^(?i)[a-z0-9]+$\")": {"str": {
                                        "$regex":"^(?i)[a-z0-9]+$"}},
        "gt(\"int\", 5)": {"int": {"$gt": 5}},
        "eq(\"bool\", true)": {"bool": True},
        "neq(\"bool\", True)": {"bool": {"$ne": True}},
        "eq(\"bool\", False)": {"bool": False},
        "neq(\"bool\", false)": {"bool": {"$ne": False}},
        "gt(\"float\", 5.0213)": {"float": {"$gt": 5.0213}},
        "le(\"float\", -5.0213)": {"float": {"$lte": -5.0213}},

        # simple cases that should fail
        "eq(,)": None,                      # empty operands
        "eq(\"str\", \"s1\", \"s2\")": None,# too many arguments
        "eq(\"str\")": None,                # missing arguments
        "eq(str, \"s1\")": None,            # attribute must be a string
        "eq(\"str\",s1)": None,             # should have double quotes
        "eq(\"str\",\"s1)": None,
        "eq(\"str\",'s1')": None,           # only support double quotes
        "eq(\"str\", \"s1\"23\")": None,    # need to escape quotes
        "regex(\"str\", \"a[\")": None,     # raise error on invalid regex
        "eq(\"x123\", \"123\")": None,      # unknown attribute name
        "abcd(\"str\", \"s1\")": None,      # unknown operator 'abcd'
        "eq(\"str\"1, \"1\")": None,        # invalid string 
        "eq(\"str\", \"str\"1)": None,      # invalid string

        # logical operators
        "and(eq(\"str\",\"1\"), eq(\"int\",5))": {"$and":[{"str":"1"},
                                                    {"int":5}]},
        "or(lt(\"int\",2),eq(\"int\",5))": {"$or": [{"int":{"$lt":2}},
                                                    {"int":5}]},
        # embedded and/or
        "and(eq(\"str\",\"1\"), or(eq(\"int\",5), eq(\"int\",7)))": {"$and":[
                    {"str":"1"}, {"$or":[{"int":5},{"int":7}]}]},
        # support more than two operators in and/or operations
        "and(eq(\"int\",1), eq(\"str\",\"1\"), eq(\"bool\",True))": {"$and":[
                                        {"int":1},{"str":"1"},{"bool":True}]},

        # logical operators that should fail
        "and(eq(\"int\",1))": None,         # require at least 2 ops for and/or
        "and(eq(\"int\",1)":None,           # missing close parentheses 
        "or(and(or(and)))":None,            # no operators provided


        # list/dict selections
        "eq(\"flatlist\", 5)": {"flatlist": 5},     # same logic as $in for list
        "eq(\"flatlist.0\", 5)": {"flatlist.0": 5}, # support list index
        "eq(\"dict.substr\",\"s1\")": {"dict.substr":"s1"},
        "eq(\"dict.subdict.sstr\", \"s1\")": {"dict.subdict.sstr": "s1"},
        "eq(\"dict.sublist.0\", 5)": {"dict.sublist.0": 5},
        "eq(\"list.subdict.sstr\", 5)": {"list.subdict.sstr": 5},
        "eq(\"list.3.subdict.sstr\", 5)": {"list.3.subdict.sstr": 5},

        "eq(\"flatlist.x\", 5)": None,      # flatlist does not have 'x' subelem
        "eq(\"list.subdict.sst3\",5)":None, # unknown subattribute
    } 

    filters2 = {
        "eq(\"flatlist.x\", 5)": None,      # flatlist does not have 'x' subelem
    }

    for k in filters:
        r = filters[k]
        logger.debug("*"*80)
        logger.debug("\tchecking [%s] == [%s]", k, r)
        if r is None: assert_bad_request(t.filter, {}, params={"filter":k})
        else: assert t.filter({}, params={"filter":k}) == r

def test_rest_api_create_invalid(app, rest_cleanup):
    # create with invalid values and ensure bad_request returned
    # refer to Rest_TestClass

    # create without required key should be a bad request
    r = app.client.post(rest_url, data=json.dumps({
        "int":5
    }), content_type='application/json')
    assert r.status_code == bad_request

    # create with unknown attribute should fail
    r = app.client.post(rest_url, data=json.dumps({
        "key":"key1",
        "unknown_attribute": 5
    }), content_type='application/json')
    assert r.status_code == bad_request

    # create with invalid value for attribute should fail
    r = app.client.post(rest_url, data=json.dumps({
        "key":"key1",
        "str": "bad_str_1235",      # regex validator on 'str' 
    }), content_type='application/json')
    assert r.status_code == bad_request

    # create key1 so duplicate fails
    r = app.client.post(rest_url, data=json.dumps({
        "key": "key1"
    }), content_type='application/json')
    assert r.status_code == good_request

    # create with duplicate key should fail
    r = app.client.post(rest_url, data=json.dumps({
        "key": "key1"
    }), content_type='application/json')
    assert r.status_code == bad_request

def test_rest_api_create_nested_dict(app, rest_cleanup):
    # perform create and ensure nested dicts are handled correctly
    # refer to Rest_TestClass

    # create with default settings
    r = app.client.post(rest_url, data=json.dumps({
        "key": "key1",
    }), content_type='application/json')

    logger.debug(r.data)
    assert r.status_code == good_request

    # read created object should be successful
    r = app.client.get(rest_url_key.format("key1"))
    assert r.status_code == good_request
    js = json.loads(r.data)
    logger.debug(pretty_print(js))
    obj = js["objects"][0]

    # ensure 'dict' attribute is present with sub-attributes according to
    # defintion and defaults
    sobj = obj[rest_classname]["dict"]
    assert isinstance(sobj, dict)
    assert "s1" in sobj and sobj["s1"] == ""
    assert "i1" in sobj and sobj["i1"] == 0
    assert "l1" in sobj and isinstance(sobj["l1"], list) and len(sobj["l1"])==0
    assert "l2" in sobj and isinstance(sobj["l2"], list)

    # second create with partial dict provided, ensure meta is correctly applied
    # to sub-attributes within list
    r = app.client.post(rest_url, data=json.dumps({
        "key": "key2",
        "str": "ABCD",
        "dict": {"l2":[{}]}
    }), content_type='application/json')
    assert r.status_code == good_request
    r = app.client.get(rest_url_key.format("key2"))
    assert r.status_code == good_request
    js = json.loads(r.data)
    logger.debug(pretty_print(js))
    sobj = js["objects"][0][rest_classname]["dict"]
    assert "l2" in sobj and isinstance(sobj["l2"], list)
    assert len(sobj["l2"]) == 1
    assert isinstance(sobj["l2"][0], dict) and \
        "ss1" in sobj["l2"][0] and sobj["l2"][0]["ss1"] == "" and \
        "ii1" in sobj["l2"][0] and sobj["l2"][0]["ii1"] == 0

    # create with unknown sub-attribute should fail
    r = app.client.post(rest_url, data=json.dumps({
        "key": "key3",
        "dict": {"unknown_sub":5},
    }), content_type='application/json')
    assert r.status_code == bad_request

    # create with unknown sub-attribute should fail
    r = app.client.post(rest_url, data=json.dumps({
        "key": "key4",
        "dict": {"l2":[{"unknown-sub-sub":1}]},
    }), content_type='application/json')
    assert r.status_code == bad_request

    # ensure validators are working on sub-sub attributes
    r = app.client.post(rest_url, data=json.dumps({
        "key": "key5",
        "dict": {"l2":[{"ii1":"abcd"}]},
    }), content_type='application/json')
    assert r.status_code == bad_request

def test_rest_api_crud_basic(app, rest_cleanup):
    # test api for Rest_Tests CRUD operations
    # refer to Rest_TestClass

    # create with only key should be successful
    r = app.client.post(rest_url, data=json.dumps({
        "key": "key1"
    }), content_type='application/json')
    assert r.status_code == good_request

    # read to created object should be successful
    r = app.client.get(rest_url_key.format("key1"))
    assert r.status_code == good_request
    js = json.loads(r.data)
    assert js["count"] == 1
    assert len(js["objects"]) == js["count"]
    obj = js["objects"][0][rest_classname]

    # assert each attribute is present with correct default value
    for k in ["key", "str", "float", "bool", "int", "list", "dict"]:
        assert k in obj
    assert obj["str"] == ""  
    assert obj["int"] == 0
    assert obj["float"] == 0.0
    assert obj["bool"] == False
    assert isinstance(obj["list"] , list) and len(obj["list"]) == 0

    assert "list2" in obj
    assert isinstance(obj["list2"], list) and len(obj["list2"]) == 0

    # perform update to subset of attributes and ensure they are updated and
    # other attributes remain the same
    r = app.client.patch(rest_url_key.format("key1"), data=json.dumps({
        "str": "ABCD",
        "int": 3,
    }), content_type='application/json')
    assert r.status_code == good_request
    obj = json.loads(r.data)
    assert obj["count"] == 1

    r = app.client.get(rest_url_key.format("key1"))
    assert r.status_code == good_request
    obj = json.loads(r.data)
    logger.debug(pretty_print(obj))
    obj = obj["objects"][0][rest_classname]
    for k in ["key", "str", "float", "bool", "int", "list", "dict"]:
        assert k in obj
    assert obj["str"] == "ABCD"  
    assert obj["int"] == 3
    assert obj["float"] == 0.0
    assert obj["bool"] == False
    assert isinstance(obj["list"] , list) and len(obj["list"]) == 0

    # perform patch for list3 which should accept list of any dict
    r = app.client.patch(rest_url_key.format("key1"), data=json.dumps({
        "list3": [
            {"a1":"value1"},
            {"a2": 2},
        ],
    }), content_type='application/json')
    assert r.status_code == good_request
    
    # perform delete
    r = app.client.delete(rest_url_key.format("key1"))
    assert r.status_code == good_request
    obj = json.loads(r.data)
    logger.debug(pretty_print(obj))
    assert obj["count"] == 1

    r = app.client.get(rest_url_key.format("key1"))
    assert r.status_code == not_found
    obj = json.loads(r.data)
    logger.debug(pretty_print(obj))

def test_rest_api_bulk_update(app, rest_cleanup):
    # perform bulk updates and ensure only specified objects are updated
    # refer to Rest_TestClass

    # create 5 objects with unique int values and ensure all present
    for x in xrange(0,5):
        r = app.client.post(rest_url, data=json.dumps({
            "key": "key%s" % x,
            "int": x
        }), content_type='application/json')
        assert r.status_code == good_request
    r = app.client.get(rest_url)
    assert r.status_code == good_request
    obj = json.loads(r.data)
    assert obj["count"] == 5

    # perform bulk update filtering on just 2-4 of the objets
    flt = "regex(\"key\",\"key[2-4]\")"
    url = "%s?filter=%s" % (rest_url, flt)
    r = app.client.patch(url, data=json.dumps({
        "int": 100    
    }), content_type='application/json')
    assert r.status_code == good_request
    obj = json.loads(r.data)
    assert obj["count"] == 3

    r = app.client.get(rest_url)
    assert r.status_code == good_request
    obj = json.loads(r.data)
    assert obj["count"] == 5
    found = {}
    for o in obj["objects"]: found[o[rest_classname]["key"]] = o[rest_classname]["int"]
    assert found["key0"] == 0
    assert found["key1"] == 1
    assert found["key2"] == 100
    assert found["key3"] == 100
    assert found["key4"] == 100

def test_rest_api_bulk_delete(app, rest_cleanup):
    # perform bulk deletes and ensure only specified objects are deleted
    # refer to Rest_TestClass

    # create 5 objects with unique int values and ensure all present
    for x in xrange(0,5):
        r = app.client.post(rest_url, data=json.dumps({
            "key": "key%s" % x,
            "int": x
        }), content_type='application/json')
        assert r.status_code == good_request
    r = app.client.get(rest_url)
    assert r.status_code == good_request
    obj = json.loads(r.data)
    assert obj["count"] == 5

    # perform bulk update filtering on just 2-4 of the objets
    flt = "regex(\"key\",\"key[2-4]\")"
    url = "%s?filter=%s" % (rest_url, flt)
    r = app.client.delete(url, data=json.dumps({
        "int": 100    
    }), content_type='application/json')
    assert r.status_code == good_request
    obj = json.loads(r.data)
    assert obj["count"] == 3

    r = app.client.get(rest_url)
    assert r.status_code == good_request
    obj = json.loads(r.data)
    assert obj["count"] == 2
    
    
def test_rest_load_object(app, rest_cleanup):
    # perform load of new object and ensure attributes are set
    T = get_test_object({
        "a1": {"type": str, "default":"string", "key":True},
        "a2": {"type": list},
        "a3": {"type": int, "default":5},
    }, return_instance = False)
    t = T.load(a1="ok")
    assert hasattr(t, "a1")
    assert hasattr(t, "a2")
    assert hasattr(t, "a3")
    assert t.a1 == "ok"
    assert isinstance(t.a2, list) and len(t.a2) == 0
    assert t.a3 == 5
    assert t.exists() is False

def test_rest_save_load_remove_new_object(app, rest_cleanup):
    # create new object and perform save to save it database
    # then perform load to ensure entry is present in the db with updated values
    # then perform remove to remove from database
    # finally perform load to ensure entry has successfully been removed
    T = get_test_object({
        "a1": {"type": str, "default":"string", "key":True},
        "a2": {"type": int, "default":0},
    }, return_instance = False)

    # ensure entry does not currently exists
    t = T.load(a1="key1")
    assert not t.exists()
    assert t.a1 == "key1"
    assert t.a2 == 0
    t.a2 = 15
    # save new value and ensure entry exists on next load
    assert t.save()
    t = T.load(a1="key1")
    assert t.exists()
    assert t.a1 == "key1"
    assert t.a2 == 15
    # remove entry from database
    assert t.remove()
    # perform second read and ensure no longer present
    t = T.load(a1="key1")
    assert not t.exists()

def test_rest_callback_create(app, rest_cleanup):
    # ensure before and after callbacks are executed for create
    T = get_test_object({
        "a1": {"type": str, "default":"string", "key":True},
        "a2": {"type": int, "default":0},
    }, return_instance = False)

    d = {"before": False, "after": False}
    def f1(**kwargs):
        # force a2 to 100 
        logger.debug("executing before create")
        obj = kwargs["data"]
        d["before"] = True
        obj["a2"] = 100
        return obj
    def f2(**kwargs):
        logger.debug("executing after create")
        obj = kwargs["data"]
        d["after"] = True
        assert obj["a2"] == 100

    T.META_ACCESS["before_create"] = f1
    T.META_ACCESS["after_create"] = f2
    obj = T.create({"a1":"key1"})
    assert obj["success"]
    assert d["before"] and d["after"]

def test_rest_callback_read(app, rest_cleanup):
    # ensure before and after callbacks are executed for read
    T = get_test_object({
        "a1": {"type": str, "default":"string", "key":True},
        "a2": {"type": int, "default":0},
        "a3": {"type": int, "default":0},
    }, return_instance = False)

    d = {"before": False, "after": False}
    def f1(**kwargs):
        # force filter to include a3=3
        logger.debug("executing before read")
        filters = kwargs["filters"]
        d["before"] = True
        filters["a3"] = 3
        return filters
    def f2(**kwargs):
        # force a3 to 5 in result
        logger.debug("executing after read")
        obj = kwargs["data"]
        d["after"] = True
        obj["objects"][0]["a3"] =5
        return obj

    T.META_ACCESS["before_read"] = f1
    T.META_ACCESS["after_read"] = f2

    # add an entry to database to perform callbacks on read
    t = T(a1="key1", a2=2, a3=4)
    assert t.save()

    # first fail will fail because entry has a3=4 but before_read forces a3=3
    assert_not_found(T.read, a1="key1")
    
    # update a3 to 3 so read will be successful
    t.a3 = 3
    assert t.save()

    r = T.read(a1="key1")
    assert r["count"] == 1
    assert r["objects"][0]["a3"] == 5
    assert d["before"] and d["after"]

def test_rest_callback_update(app, rest_cleanup):
    # ensure before and after callbacks are executed for update
    T = get_test_object({
        "a1": {"type": str, "default":"string", "key":True},
        "a2": {"type": int, "default":0},
        "a3": {"type": int, "default":0},
    }, return_instance = False)

    d = {"before": False, "after": False}
    def f1(**kwargs):
        # force data to set a3 to 100
        logger.debug("executing before update")
        filters = kwargs["filters"]
        data = kwargs["data"]
        d["before"] = True
        data["a3"] = 100
        return (filters, data)
    def f2(**kwargs):
        # the data should have a3 updated to 100
        logger.debug("executing after update")
        filters = kwargs["filters"]
        data = kwargs["data"]
        d["after"] = True
        assert data["a3"] == 100

    T.META_ACCESS["before_update"] = f1
    T.META_ACCESS["after_update"] = f2

    # add an entry to database to perform callbacks on read
    t = T(a1="key1", a2=2, a3=4)
    assert t.save()

    # perform update to a2 and set value to 5, then read and ensure a3 was
    # manually set to 100 through before_update
    _data = {"a2": 5}
    r = T.update(_data, a1="key1")
    assert r["success"]
    
    t = T.load(a1="key1")
    logger.debug(t)
    assert t.a2 == 5
    assert t.a3 == 100
    assert d["before"] and d["after"]

def test_rest_callback_delete(app, rest_cleanup):
    # ensure before and after callbacks are executed for delete
    T = get_test_object({
        "a1": {"type": str, "default":"string", "key":True},
        "a2": {"type": int, "default":0},
        "a3": {"type": int, "default":0},
    }, return_instance = False)

    d = {"before": False, "after": False}

    def f1(**kwargs):
        # force filter to include a3=3
        logger.debug("executing before delete")
        filters = kwargs["filters"]
        d["before"] = True
        filters["a3"] = 3
        return filters
    def f2(**kwargs):
        # ensure a3 has been set to 3
        logger.debug("executing after delete")
        filters = kwargs["filters"]
        d["after"] = True
        assert filters["a3"] == 3

    T.META_ACCESS["before_delete"] = f1
    T.META_ACCESS["after_delete"] = f2

    # create entry with a3=1 and perform delete which should abort not found
    # since a3 was not matched
    t = T(a1="key1", a2=2, a3=1)
    assert t.save()
    assert_not_found(T.delete, a1="key1")

    t.a3 = 3
    assert t.save()
    r = T.delete(a1="key1")
    assert r["count"] == 1
    assert d["before"] and d["after"]

def test_rest_hash_attribute(app, rest_cleanup):
    # check that hash attribute is correctly applied and can be matched with check_password_hash
    # also verify updates to hash are applied correctly through model

    from flask_bcrypt import check_password_hash

    # create an object with hash 'hash1' and save
    t = Rest_Secure.load(key="key1")
    t.hash = "hash1"
    assert t.save()

    # read back the object
    t = Rest_Secure.load(key="key1")
    assert t.exists()
    logger.debug("original hash: %s", t.hash)
    assert check_password_hash(t.hash, "hash1")

    # update the hash to 'hash2' and recheck
    t.hash = "hash2"
    assert t.save()
    t = Rest_Secure.load(key="key1")
    assert t.exists()
    logger.debug("updated hash: %s", t.hash)
    assert check_password_hash(t.hash, "hash2")

def test_rest_encrypt_attribute(app, rest_cleanup):
    # check that we're able to encrypt/decrypt values in the database for encrypt attributes

    t = Rest_Secure.load(key="key1")
    t.encrypt = "encrypt"
    assert t.save()

    # perform db read and ensure value is encrypted
    ret = app.db.test.secure.find({"key":"key1"})
    obj = None
    for o in ret:
        obj = o
        break
    assert obj is not None
    logger.debug("raw db read result: %s", obj)
    assert obj["encrypt"] != "encrypt"

    t = Rest_Secure.load(key="key1")
    logger.debug("db result for object: %s", t)
    assert t.exists()
    assert t.encrypt == "encrypt"
    
def test_rest_update_no_change(app, rest_cleanup):
    # this test uses .save() method to create a new instance of an object and then calls the save()
    # again when no changes have occurred.  This should return a success and no update should occur
    # to the DB

    t = Rest_Secure.load(key="key1")
    assert t.save()
    assert t.save()    





