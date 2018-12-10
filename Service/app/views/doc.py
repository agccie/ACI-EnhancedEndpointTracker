
from flask import Blueprint
doc = Blueprint("doc", __name__)

from flask import send_from_directory

@doc.route("/")
def documentation_base():
    return send_from_directory("static/swagger", "index.html")

@doc.route("/<path:path>")
def documentation(path):
    return send_from_directory("static/swagger", path)

