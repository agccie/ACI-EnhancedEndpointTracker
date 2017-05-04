
from flask import current_app, Blueprint, render_template, jsonify
doc = Blueprint("doc", __name__)

from flask_login import login_required, current_user
from flask import request, make_response, g, abort
from ..models.roles import Roles
import json, hashlib, re

# functions that require documentation need only to import doc.autodoc and
# call decorator @doc.autodoc.doc()
from flask.ext.autodoc import Autodoc
autodoc = Autodoc()

@doc.route("/")
@login_required
def documentation():
    # dict: autodoc.generate()
    data = autodoc.generate()
    result = {}     # indexed by docstring attribute hash
                    # where each entry has 'endpoint', 'docstring', 'urls'
                    # and each url has 'methods' and 'rule' attributes
    req = ["endpoint", "docstring", "methods", "rule"]
    for d in data:
        valid_doc = True
        for r in req: 
            if r not in d: valid_doc = False
        if not valid_doc: continue
        if d["docstring"] is None: continue
        key = hashlib.md5(d["docstring"]).hexdigest()
        if key not in result: 
            result[key] = {
                "docstring": "\n".join([
                    re.sub("^       ","", l) \
                    for l in d["docstring"].split("\n")]),
                "urls": [],
                "index": None,
            }
        methods = []
        for m in d["methods"]:
            if m in ["GET", "POST", "PUT", "DELETE"]: methods.append(m)
        methods = ", ".join(sorted(methods))
        # fix up 
        result[key]["urls"].append({
            "endpoint": d["endpoint"],
            "methods": methods,
            "rule": d["rule"]
        })
        if result[key]["index"] is None or \
            len(result[key]["index"]) > len(d["rule"]):
            result[key]["index"] = d["rule"]

    sorted_result = []
    for k in sorted(result, key= lambda i: result[i]["index"]):
        result[k]["id"] = ("%s%s" % (
            re.sub(" ","",result[k]["urls"][0]["methods"]),
            result[k]["index"] )).lower()
        sorted_result.append(result[k])

    # ensure user is full admin
    if g.user.role != Roles.FULL_ADMIN: abort(403)
    return render_template("doc/doc.html", api=sorted_result)
