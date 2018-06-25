
import logging
from ..rest import (Rest, api_register, registered_classes)
from flask import jsonify, current_app

def get_swagger_documentation():
    """ get swagger documentation for all rest endpoints """
    swagger = {
        "openapi": "3.0.0",
        "info": {
            "description": "Provide general API documentation",
            "version": "1.0.1",
            "title": "API Documentation",
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
            perform advanced filtering on attributes to limit the number of 
            objects read or modified.
            See filter query syntax [link](https://www.google.com)
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
                    sort attribute along with optional sort direction. The sort
                    directions are 'asc' and 'desc' with default of 'asc'. For 
                    example, to sort users by username and then by last_login:
                        sort=username,last_login|desc
                    """.strip()
                },
                "count": {
                    "in": "query",
                    "name": "count",
                    "schema": {"type": "boolean"},
                    "description": """
                    return only the number of objects matching the query. Note,
                    this is performed if 'count' parameter is present 
                    independent of whether the value is true or false
                    """.strip()
                },
                "include": {
                    "in": "query",
                    "name": "include",
                    "schema": {"type": "string"},
                    "description": """
                    comma separated list of attributes to include in read 
                    result. By default all object attributes are returned. For
                    example: include=compare_id,total
                    Note, if _id is exposed then it is always returned with 
                    result even if not provided in list of include attributes.
                    """.strip()
                },
            },
            "schemas": {
                "generic_write": {
                    "type": "object",
                    "properties": {
                        "successs":{
                            "type": "boolean",
                            "description": "successfully created object"
                        },
                        "count": {
                            "type": "integer",
                            "description": "number of objects modified"
                        },
                    },
                },
                "generic_post": {
                    "type": "object",
                    "properties": {
                        "successs":{
                            "type": "boolean",
                            "description": "successfully performed post"
                        },
                        "error": {
                            "type": "string",
                            "description": "description of error if not success"
                        },
                    },
                },
                "create_id": {
                    "type": "object",
                    "properties": {
                        "successs":{
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
                "read": {
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "number of objects returned"
                        },
                        "objects": {
                            "type": "array",
                            "description": "list of objects returned"
                        },
                    },
                },
                "bad_request": {
                    "type": "object",
                    "description": """ if a create/read/update/delete operation
                    fails validation then a 400 badRequest is returned with a
                    description regarding what validation failed. """,
                    "properties": {
                        "error": {
                            "type": "string",
                            "description": "description of error"
                        },
                    },
                },
            }
        },
        "definitions": {}
    }

    for c in registered_classes:
        c = registered_classes[c]
        for p in c._swagger: 
            swagger["paths"][p] = c._swagger[p]

    return jsonify(swagger)



@api_register()
class Docs(Rest):

    # allow only read and update requests
    META_ACCESS = {
        "read": False,
        "create": False,
        "update": False,
        "delete": False,
        "routes": [
            {
                "path":"/",
                "methods": ["GET"],
                "function": get_swagger_documentation
            }
        ],
    }
    
