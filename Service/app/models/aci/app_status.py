
import logging, os
from flask import jsonify, g, abort, current_app
from ..rest import (Rest, api_register)

logger = logging.getLogger(__name__)

def check_status():
    # check the current status of the app by reading started/status files
    # set by container start.sh script.  One of three status codes returned:
    #   500 (this occurs if apache hasn't started and script is never called)
    #   400 (.started not yet set, status includes whatever is in .status file)
    #   200 started
    status = ""
    if os.path.exists(current_app.config["ACI_STARTED_FILE"]):
        logger.debug("application started flag is set")
        return jsonify({"status":"started"})
    logger.debug("application started flag not found, checking for status")
    if os.path.exists(current_app.config["ACI_STATUS_FILE"]):
        try:
            with open(current_app.config["ACI_STATUS_FILE"], "r") as f:
                status = f.read()
                logger.debug("application status: %s" % status)
        except Exception as e:
            logger.debug("failed to open status file: %s" % e)
    else:
        logger.debug("application status flag not found")
        status = "not-ready"
    abort(400, status)

@api_register(path="/aci/app-status")
class AppStatus(Rest):
    META_ACCESS = {
        "read": False,
        "create": False,
        "update": False,
        "delete": False,
        "routes": [
            {
                "path":"/",
                "methods": ["GET"],
                "function": check_status
            }
        ],
    }
