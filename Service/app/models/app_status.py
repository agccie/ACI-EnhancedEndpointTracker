
from . aci.ept.ept_msg import eptMsg
from . aci.ept.ept_msg import MSG_TYPE
from . aci.ept.common import MANAGER_CTRL_CHANNEL 
from . aci.ept.common import MANAGER_CTRL_RESPONSE_CHANNEL 
from . aci.ept.common import get_random_sequence
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
    1 of queue_len represents pending messages for queues at index 1. With support for batch msgs,
    a single message in the queue may be contain up to 10K additional mesages.
    """,
}

@api_register(path="/app-status")
class AppStatus(Rest):
    """ validate that all required backend services are running for this application """

    # timeout for manager status with accurate count to inspect all inflight msgs may be a while...
    MANAGER_STATUS_TIMEOUT = 3.0
    MANAGER_STATUS_BRIEF_TIMEOUT = 1.5

    META_ACCESS = {
        "read": False,
        "create": False,
        "update": False,
        "delete": False,
        "read_role": Role.USER,
    }
    META = {
        # for api swagger reference only
        "version": {
            "reference": True,
            "type": dict,
            "description": "app version information",
            "meta": {
                "version": {
                    "type": str,
                    "description": "app version",
                },
                "app_id": {
                    "type": str,
                    "description": "app name/id",
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
                "contact_email": {
                    "type": str,
                    "description": "contact email address"
                },
                "contact_url": {
                    "type": str,
                    "description": "contact url"
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
                            "description": "manager status (starting|running|stopped)",
                            "values": ["starting", "running", "stopped"],
                        },
                        "manager_id": {
                            "type": str,
                            "description": "unique id for manager process",
                        },
                        "queues": queues_meta,
                        "queue_len": queue_len_meta,
                    },
                },
                "total_queue_len": {
                    "type": int,
                    "description": """sum of all inflight messages across all queues"""
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
        "total_queue_len": {
            "reference": True,
            "type": int,
            "description": """sum of all inflight messages across all queues""",
        },
        "addr": {
            "reference": True,
            "type": str,
            "regex": "^[0-9a-z\.\:]{2,64}",
            "description": """ 
            IP or mac address string for hash check. Note, for accurate results ensure MAC addresses
            are in upper-case format (AA:BB:CC:DD:EE:FF), IPv4 address are in standard dotted-decimal
            format (W.X.Y.Z), and IPv6 addresses are in lower-case format (2001::a:b:c:d)
            """
        },
        "hash": {
            "reference": True,
            "type": int,
            "description": """ address hash calculation result """,
        },
        "index": {
            "reference": True,
            "type": int,
            "description": """ index of worker from hash calculation """,
        },
        "worker": {
            "reference": True,
            "type": str,
            "description": """ worker selected by hash/index for provided address """,
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
            "app_id": current_app.config.get("APP_ID", ""),
            "commit": current_app.config.get("APP_COMMIT", ""),
            "date": current_app.config.get("APP_COMMIT_DATE", ""),
            "timestamp": current_app.config.get("APP_COMMIT_DATE_EPOCH", 0),
            "branch": current_app.config.get("APP_COMMIT_BRANCH", ""),
            "author": current_app.config.get("APP_COMMIT_AUTHOR", ""),
            "contact_url": current_app.config.get("APP_CONTACT_URL", ""),
            "contact_email": current_app.config.get("APP_CONTACT_EMAIL", ""),
        })

    @staticmethod
    @api_route(path="/manager", methods=["GET"], role="read_role", swag_ret=["manager_status"])
    def api_check_manager_status():
        """ check status of manager process including all active fabrics """
        try:
            ret = AppStatus.check_manager_status()
            if ret is not None:
                return jsonify(ret)
        except Exception as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        abort(500, "failed to send message or invalid manager response")

    @staticmethod
    @api_route(path="/queue", methods=["GET"], role="read_role", swag_ret=["total_queue_len"])
    def api_get_queue_len():
        """ get total number of pending work events across all queues """
        try:
            ret = AppStatus.check_manager_status(brief=False)
            if ret is not None:
                return jsonify({"total_queue_len": ret.get("total_queue_len", 0)})
        except Exception as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        abort(500, "failed to send message or invalid manager response")

    @staticmethod
    def check_fabric_is_alive(fabric):
        """ check status of single fabric from manager perspective. If no response is received
            after timeout then False is returned.  Else, corresponding alive status is returned.
        """
        seq = get_random_sequence()
        msg = eptMsg(MSG_TYPE.GET_FABRIC_STATUS, seq=seq, data={"fabric":fabric})
        logger.debug("get fabric status (seq:0x%x) fabric: %s", seq, fabric)
        redis = get_redis()
        p = redis.pubsub(ignore_subscribe_messages=True)
        p.subscribe(MANAGER_CTRL_RESPONSE_CHANNEL)
        redis.publish(MANAGER_CTRL_CHANNEL, msg.jsonify())
        start_ts = time.time()
        timeout = AppStatus.MANAGER_STATUS_BRIEF_TIMEOUT
        try:
            while start_ts + timeout > time.time():
                data = p.get_message(timeout=0.5)
                if data is not None:
                    channel = data["channel"]
                    if channel == MANAGER_CTRL_RESPONSE_CHANNEL:
                        msg = eptMsg.parse(data["data"]) 
                        if msg.msg_type == MSG_TYPE.FABRIC_STATUS:
                            # validate this is the addr and sequence number our user requested
                            if msg.seq == seq and "fabric" in msg.data and \
                                msg.data["fabric"] == fabric:
                                logger.debug("fabric status (0x%x) alive:%r", seq, msg.data["alive"])
                                if msg.data["alive"]: 
                                    return True
                                else:
                                    return False
                            else:
                                logger.debug("rx seq/fabric (0x%x/%s), expected (0x%x/%s)",
                                    msg.seq, msg.data.get("fabric", ""), seq, fabric)
        except Exception as e:
            logger.debug("Traceback:\n%s", traceback.format_exc())
            logger.debug("error: %s", e)
        finally:
            if redis is not None and hasattr(redis, "connection_pool"):
                redis.connection_pool.disconnect()
        logger.warn("no manager response within timeout(%s sec)", timeout)
        return False

    @staticmethod
    def check_manager_status(brief=True):
        """ check status of manager process including all active fabrics 
            to do this, need to setup a listener on MANAGER_CTRL_CHANNEL and listen for 
            MANAGER_STATUS message. This should be seen immediately but will wait up to 
            AppStatus.MANAGER_STATUS_TIMEOUT threshold or MANAGER_STATUS_BRIEF_TIMEOUT
            Set brief to True to exclude queue statistics.
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
            "total_queue_len": 0,
        }
        seq = get_random_sequence()
        msg = eptMsg(MSG_TYPE.GET_MANAGER_STATUS, seq=seq, data={"brief": brief})
        logger.debug("get manager status (seq:0x%x) brief:%r", seq, brief)
        redis = get_redis()
        p = redis.pubsub(ignore_subscribe_messages=True)
        p.subscribe(MANAGER_CTRL_RESPONSE_CHANNEL)
        redis.publish(MANAGER_CTRL_CHANNEL, msg.jsonify())
        start_ts = time.time()
        timeout = AppStatus.MANAGER_STATUS_TIMEOUT 
        try:
            if brief:
                timeout = AppStatus.MANAGER_STATUS_BRIEF_TIMEOUT
            while start_ts + timeout > time.time():
                data = p.get_message(timeout=1)
                if data is not None:
                    channel = data["channel"]
                    if channel == MANAGER_CTRL_RESPONSE_CHANNEL:
                        msg = eptMsg.parse(data["data"]) 
                        if msg.msg_type == MSG_TYPE.MANAGER_STATUS:
                            logger.debug("received manager status (seq:0x%x)", msg.seq)
                            ret["manager"] = msg.data["manager"]
                            ret["workers"] = msg.data["workers"]
                            ret["fabrics"] = msg.data["fabrics"]
                            ret["total_queue_len"] = msg.data["total_queue_len"]
                            return ret
        except Exception as e:
            logger.debug("Traceback:\n%s", traceback.format_exc())
            logger.debug("error: %s", e)
        finally:
            if redis is not None and hasattr(redis, "connection_pool"):
                redis.connection_pool.disconnect()

        logger.warn("no manager response within timeout(%s sec)", timeout)
        return ret

    @staticmethod
    @api_route(path="/hash", methods=["POST"], role="read_role", swag_ret=["addr","hash","index",
                "worker"])
    def api_get_address_hash(addr):
        """ check status of manager process including all active fabrics """
        try:
            ret = AppStatus.get_address_hash(addr)
            if ret is not None:
                return jsonify(ret)
        except Exception as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        abort(500, "failed to send message or invalid manager response")

    @staticmethod
    def get_address_hash(addr):
        """ return calculated hash and worker index for provided address string and worker count """
        ret = {
            "addr": addr,
            "hash": 0,
            "index": 0,
            "worker": "",
        }
        seq = get_random_sequence()
        logger.debug("get addr hash (seq:0x%x, addr:%s)", seq, addr)
        tx_msg = eptMsg(MSG_TYPE.GET_WORKER_HASH, data={"addr":addr}, seq=seq)
        redis = get_redis()
        p = redis.pubsub(ignore_subscribe_messages=True)
        p.subscribe(MANAGER_CTRL_RESPONSE_CHANNEL)
        redis.publish(MANAGER_CTRL_CHANNEL, tx_msg.jsonify())
        start_ts = time.time()
        try:
            while start_ts + AppStatus.MANAGER_STATUS_TIMEOUT > time.time():
                data = p.get_message(timeout=1)
                if data is not None:
                    channel = data["channel"]
                    if channel == MANAGER_CTRL_RESPONSE_CHANNEL:
                        msg = eptMsg.parse(data["data"]) 
                        if msg.msg_type == MSG_TYPE.WORKER_HASH:
                            logger.debug("received addr hash response (seq:0x%x)", msg.seq)
                            # validate this is the addr and sequence number our user requested
                            if msg.seq == seq and "addr" in msg.data and msg.data["addr"] == addr:
                                ret["hash"] = msg.data.get("hash", 0)
                                ret["index"] = msg.data.get("index", 0)
                                ret["worker"] = msg.data.get("worker", "")
                                return ret
                            else:
                                logger.debug("rx hash (0x%x/%s) incorrect, expected (0x%x/%s)",
                                    msg.seq, msg.data.get("addr", 0), seq, addr)
        except Exception as e:
            logger.debug("Traceback:\n%s", traceback.format_exc())
            logger.debug("error: %s", e)
        finally:
            if redis is not None and hasattr(redis, "connection_pool"):
                redis.connection_pool.disconnect()

