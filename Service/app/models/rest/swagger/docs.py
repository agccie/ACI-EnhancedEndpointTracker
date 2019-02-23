
from ... utils import get_app_config
from .. import Rest
from .. import api_register
from .. import api_route
from .. import registered_classes
from flask import Blueprint
from flask import jsonify
from flask import send_from_directory
import logging
import os

# module level logging
logger = logging.getLogger(__name__)
swagger_ui_dir= os.path.abspath("%s/swagger-ui" % os.path.dirname(os.path.realpath(__file__)))

swagger_doc = Blueprint("doc", __name__)

@swagger_doc.route("/")
def documentation_base():
    logger.debug(swagger_ui_dir)
    return send_from_directory(swagger_ui_dir, "index.html")

@swagger_doc.route("/<path:path>")
def documentation(path):
    return send_from_directory(swagger_ui_dir, path)

@api_register(path="/docs/")
class Docs(Rest):

    META_ACCESS = {
        "read": False,
        "create": False,
        "update": False,
        "delete": False,
        "doc_enable": False,
    }
   
    @api_route(path="/", methods=["GET"], authenticated=False)
    def get_swagger_documentation():
        """ get swagger documentation for all rest endpoints """
        config = get_app_config()
        app_id = config.get("APP_ID", "")
        app_contact_email = config.get("APP_CONTACT_EMAIL", "")
        app_contact_url = config.get("APP_CONTACT_URL", "")
        app_full_version = config.get("APP_FULL_VERSION", "1.0")
        swagger = {
            "openapi": "3.0.0",
            "info": {
                "description": """
This documentation details the externally accessible APIs. Each API endpoint may have different 
authentication and authorization (role) requirements. Authorized endpoints require a `session` 
token provided in either a cookie or within the HTTP header. For additional security, a challenge 
token can also be requested and will be required in all subsequent requests as a header named 
`app-token`. Refer to the **User** login section for more details.
                """,
                "version": app_full_version,
                "title": "%s API Documentation" % app_id,
                "contact":{
                    "email": app_contact_email,
                    "url": app_contact_url,
                }
            },
            "servers": [
                { "url": "/api" },
            ],
            "paths": {},
            "components": {
                "parameters": {
                    "filter": {
                        "in": "query",
                        "name": "filter",
                        "required": False,
                        "schema": { "type": "string"},
                        "description": """
Filters allow user to perform advanced filtering on attributes to limit the number of objects 
read or modified.  **Note** objects that support `bulk update` and `bulk delete` can utilize 
the same filter syntax to modify or delete a range of objects.
    
There are two types of operators supported:
* **base-operators** in the form `operator`("`attribute`", `value`)
        * `eq` filters on attributes equal to `value`
        * `neq` filters on attributes not equal to `value`
        * `lt` filters on attributes less than `value`
        * `le` filters on attributes less than or equal to `value`
        * `gt` filters on attributes greater than `value`
        * `ge` filters on attributes greater than or equal to `value`
        * `regex` filters on attributes with `value` matching a regular expression
* **conditional-operators** in the form `operator`(`op1`, `op2`).  Here `op1` and `op2` can be a
base-operator or another conditional-operator.
        * `and` filter condition when both `op1` and `op2` evaluate to True
        * `or` filter condition when either `op1` or `op2` evaluate to True
    
Below are **example filters** for a User object that contains a string attribute `username` and
float timestamp `last_login`:
* Show only user info for username `admin` or `root`:
        * `or`( `eq`(`"username"`, `"admin"`) , `eq` (`"username"`, `"root"`) )
* Show only users `username` that contains `mgmt`:
        * `regex` (`"username"`, `"mgmt"`)
* Show only users with `last_login` after Aug-22-2018 (epoch timestamp `1534896000`):
        * `ge` (`"last_login"`, `1534896000`)
                        """.strip()
                    },
                   "page": {
                        "in": "query",
                        "name": "page",
                        "schema": {"type": "integer"},
                        "description": "page to return (default is page 0)"
                    },
                    "page-size": {
                        "in": "query",
                        "name": "page-size",
                        "schema": {"type": "integer"},
                        "description":"number of objects per page (default is 1000)"
                    },
                    "sort": {
                        "in": "query",
                        "name": "sort",
                        "schema": {"type": "string"},
                        "description": """
                            sort attribute along with optional sort direction. The sort directions 
                            are 'asc' and 'desc' with default of 'asc'. For example, to sort users 
                            by username and then by last_login:
                            <strong>sort=username,last_login|desc</strong>
                        """.strip()
                    },
                    "count": {
                        "in": "query",
                        "name": "count",
                        "schema": {"type": "boolean"},
                        "description": """
                            return only the number of objects matching the query. Note, this is
                            performed if 'count' parameter is present independent of whether the 
                            value is true or false
                        """.strip()
                    },
                    "include": {
                        "in": "query",
                        "name": "include",
                        "schema": {"type": "string"},
                        "description": """
                            comma separated list of attributes to include in read result. By default
                            all object attributes are returned. For example:
                            <strong>include=compare_id,total</strong><br>
                            Note, if _id is exposed then it is always returned with result even if 
                            not provided in list of include attributes. 
                        """.strip()
                    },
                    "rsp-include": {
                        "in": "query",
                        "name": "rsp-include",
                        "schema": {"type": "string", "enum":["self","children","subtree"]},
                        "description": """
                            Include children or full subtree in response. By default, only the 
                            object matching the provided query filter is returned.
                        """.strip()
                    },
                },
                "schemas": {
                    "create_response": {
                        "type": "object",
                        "properties": {
                            "success":{
                                "type": "boolean",
                                "description": "successfully created object"
                            },
                            "count": {
                                "type": "integer",
                                "description": "number of objects modified"
                            },
                        },
                    },
                    "create_id_response": {
                        "type": "object",
                        "properties": {
                            "success":{
                                "type": "boolean",
                                "description": "successfully created object"
                            },
                            "count": {
                                "type": "integer",
                                "description": "number of objects modified"
                            },
                            "_id": {
                                "type": "string",
                                "description": "string objectId of new object"
                            },
                        },
                    },
                }
            },
            "definitions": {},
            "tags": {},
        }
    
        for c in sorted(registered_classes):
            c = registered_classes[c]
            if c._access["doc_enable"]:
                if "read_obj_ref" in c._swagger:
                    swagger["components"]["schemas"][c._classname] = c._swagger["read_obj_ref"]
                for p in c._swagger:
                    swagger["paths"][p] = c._swagger[p]
                # add global 'tags' to swagger with description of class
                swagger["tags"][c._classname] = {
                    "name": c._classname,
                    "description": c._access["description"],
                }
        return jsonify(swagger)

