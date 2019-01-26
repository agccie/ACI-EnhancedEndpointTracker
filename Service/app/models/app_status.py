
from . aci.ept.ept_msg import eptMsg
from . aci.ept.ept_msg import MSG_TYPE
from . aci.ept.common import MANAGER_CTRL_CHANNEL 
from . rest import api_register
from . rest import api_route
from . rest import Rest
from . rest import Role
from . utils import get_redis

from flask import jsonify
from flask import abort
from flask import current_app

import logging
import os
import time
import traceback

# module level logger
logger = logging.getLogger(__name__)

queues_meta = {
    "type": list,
    "subtype": str,
    "description": "list of queues for process ordered with highest priority queue first",
}
queue_len_meta = {
    "type": list,
    "subtype": int,
    "description": """
    number of pending messages in queue. Note, queue_len uses same indexed as queues.  I.e., index
    1 of queue_len represents pending messages for queues at index 1
    """,
}

@api_register(path="/app-status")
class AppStatus(Rest):
    """ validate that all required backend services are running for this application """

    MANAGER_STATUS_TIMEOUT = 3

    META_ACCESS = {
        "read": False,
        "create": False,
        "update": False,
        "delete": False,
        "read_role": Role.USER,
    }
    META = {
        "version": {
            "reference": True,
            "type": dict,
            "description": "app version information",
            "meta": {
                "version": {
                    "type": str,
                    "description": "app version",
                },
                "commit": {
                    "type": str,
                    "description": "git commit hash",
                },
                "date": {
                    "type": str,
                    "description": "ISO timestamp of git commit"
                },
                "timestamp": {
                    "type": float,
                    "description": "EPOCH timestamp of git commit",
                },
                "branch": {
                    "type": str,
                    "description": "branch name of git commit",
                },
                "author": {
                    "type": str,
                    "description": "author email of git commit",
                },
            },
        },
        "manager_status": {
            "reference": True,
            "type": dict,
            "description": "manager process status",
            "meta": {
                "fabrics": {
                    "type": list,
                    "description": "list of fabric monitors actively tracked by manager",
                    "subtype": dict,
                    "meta": {
                        "fabric": {
                            "type": str,
                            "description": "fabric identifier",
                        },
                        "alive": {
                            "type": bool,
                            "description": "fabric is actively running",
                        },
                    },
                },
                "manager": {
                    "type": dict,
                    "description": "container for manager info",
                    "meta": {
                        "status":{
                            "type": str,
                            "description": "manager status (running|stopped)",
                            "values": ["running", "stopped"],
                        },
                        "manager_id": {
                            "type": str,
                            "description": "unique id for manager process",
                        },
                        "queues": queues_meta,
                        "queue_len": queue_len_meta,
                    },
                },
                "workers": {
                    "type": list,
                    "subtype": dict,
                    "meta": {
                        "active": {
                            "type": bool,
                            "description": "worker is actively registered and in use by manager",
                        },
                        "hello_seq": {
                            "type": int,
                            "description": "last hello sequence received from worker",
                        },
                        "last_seq": {
                            "type": list,
                            "subtype": int,
                            "description": "list of last sequence numbers sent on each worker queue",
                        },
                        "queues": queues_meta,
                        "queue_len": queue_len_meta,
                        "role": {
                            "type": str,
                            "description": "worker role",
                            "values": ["worker", "priority", "watcher"],
                        },
                        "start_time": {
                            "type": float,
                            "description": "epoch timestamp when worker process started",
                        },
                        "worker_id": {
                            "type": str,
                            "description": "unique id for worker process",
                        },
                    },
                },
            },
        },
    }

    @staticmethod
    @api_route(path="/", methods=["GET"], authenticated=False, swag_ret=["success", "error"])
    def api_check_status():
        """ check the startup status of the app. A 500 error may occur if the webserver is not 
            running or app is not ready.  A 503 service unavailable is return if not ready with an
            error description
        """
        (success, status) = AppStatus.check_status()
        if success: return jsonify({"success": True})
        abort(503, status)

    @staticmethod
    def check_status():
        """ check status and return tuple (bool, description) where bool is True if running 
            also validate mongo db and redis db are alive (may be deployed in different containers)
        """
        status = ""
        if os.path.exists(current_app.config["ACI_STARTED_FILE"]):
            logger.debug("application started flag is set")
            # check mongo connection 
            try:
                from . utils import get_db
                assert len(get_db().collection_names()) >= 0
            except Exception as e:
                logger.debug("failed to connect to mongo db: %s", e)
                return (False, "failed to connect to mongo database")
            # check redis connection
            try:
                from . utils import get_redis
                assert get_redis().dbsize() >= 0
            except Exception as e:
                logger.debug("failed to connect to redis db: %s", e)
                return (False, "failed to connect to redis database")
            # started flag and successfully connected to mongo and redis
            return (True, "started")

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
        return (False, status)

    @staticmethod
    @api_route(path="/version", methods=["GET"], authenticated=False, swag_ret=["version"])
    def get_version():
        """ get app version and build info """
        version = current_app.config.get("APP_FULL_VERSION", "")
        if len(version) == 0: 
            version = current_app.config.get("APP_VERSION", "")
        return jsonify({
            "version": version,
            "commit": current_app.config.get("APP_COMMIT", ""),
            "date": current_app.config.get("APP_COMMIT_DATE", ""),
            "timestamp": current_app.config.get("APP_COMMIT_DATE_EPOCH", 0),
            "branch": current_app.config.get("APP_COMMIT_BRANCH", ""),
            "author": current_app.config.get("APP_COMMIT_AUTHOR", ""),
        })

    @staticmethod
    @api_route(path="/manager", methods=["GET"], role="read_role", swag_ret=["manager_status"])
    def api_check_manager_status():
        """ check status of manager process including all active fabrics """
        try:
            return jsonify(AppStatus.check_manager_status())
        except Exception as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
            abort(500, "failed to send message or invalid manager response")

    @staticmethod
    def check_manager_status():
        """ check status of manager process including all active fabrics 
            to do this, need to setup a listener on MANAGER_CTRL_CHANNEL and listen for 
            MANAGER_STATUS message. This should be seen immediately but will wait up to 
            AppStatus.MANAGER_STATUS_TIMEOUT threshold
        """
        ret = {
            "manager": {
                "manager_id": None,
                "queues": [],
                "queue_len": [],
                "status": "stopped",
            },
            "workers": [],
            "fabrics": [],
        }
        redis = get_redis()
        p = redis.pubsub(ignore_subscribe_messages=True)
        p.subscribe(MANAGER_CTRL_CHANNEL)
        redis.publish(MANAGER_CTRL_CHANNEL, eptMsg(MSG_TYPE.GET_MANAGER_STATUS).jsonify())
        start_ts = time.time()
        try:
            while start_ts + AppStatus.MANAGER_STATUS_TIMEOUT > time.time():
                data = p.get_message(timeout=1)
                if data is not None:
                    channel = data["channel"]
                    if channel == MANAGER_CTRL_CHANNEL:
                        msg = eptMsg.parse(data["data"]) 
                        if msg.msg_type == MSG_TYPE.MANAGER_STATUS:
                            ret["manager"] = msg.data["manager"]
                            ret["manager"]["status"] = "running"
                            ret["workers"] = msg.data["workers"]
                            ret["fabrics"] = msg.data["fabrics"]
                            return ret
        except Exception as e:
            logger.debug("Traceback:\n%s", traceback.format_exc())
            logger.debug("error: %s", e)
        finally:
            if redis is not None and hasattr(redis, "connection_pool"):
                redis.connection_pool.disconnect()

        logger.warn("no manager response within timeout(%s sec)", AppStatus.MANAGER_STATUS_TIMEOUT)
        return ret


