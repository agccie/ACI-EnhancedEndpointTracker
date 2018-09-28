
from .. app_status import AppStatus
from .. rest import Rest
from .. rest import Role
from .. rest import api_register
from .. rest import api_route
from .. rest import api_callback
from .. utils import get_app_config
from .. utils import get_redis

from . import utils as aci_utils
from . ept.ept_msg import eptMsg
from . ept.ept_msg import MSG_TYPE
from . ept.common import MANAGER_CTRL_CHANNEL 

from flask import abort
from flask import jsonify

import json
import logging
import os
import re
import redis
import requests
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

@api_register(path="/fabric")
class Fabric(Rest):
    """ ACI Fabric REST class """

    logger = logger
    # meta data and type that are exposed via read/write 
    META_ACCESS = {
        "default_role": Role.FULL_ADMIN
    }
    META = {
        "fabric":{
            "key": True,
            "type":str, 
            "default":"", 
            "key_sn": "fb",
            "regex":"^[a-zA-Z0-9\-\.:_]{1,64}$",
            "description": "fabric name",
        },
        "apic_username":{
            "type":str, 
            "default":"admin",
            "regex":"^[a-zA-Z0-9\-_\.@]{1,128}$",
            "description": "APIC username",
        },
        "apic_password":{
            "type": str, 
            "default": "",
            "read": False,
            "encrypt": True,
            "description": "APIC password for token based authentication",
        },
        "apic_hostname":{
            "type":str, 
            "description": "APIC hostname or IP address",
        },
        "apic_cert": {
            "type":str,
            "description": "path to APIC private-key for cert-based authentication",
        },
        "ssh_username":{
            "regex":"^[a-zA-Z0-9\-_\.@]{0,128}$",
            "default": "admin",
            "description": "username for ssh access to switch",
        },
        "ssh_password":{
            "encrypt": True,
            "read": False,
            "description": "password for ssh access to switch",
        },
        "auto_start": {
            "type": bool,
            "write": False,
            "default": False,
            "description": "auto start when application starts or auto restart on failure",
        },
        "controllers": {
            "type":list,
            "subtype": str,
            "write": False,
            "description": "dynamically discovered out-of-band or inband ipv4 management addresses",
        },
        # history of events with most recent event at the beginning
        "events": {
            "type": list,
            "write": False,
            "description": "list of fabric monitoring events",
            "subtype": dict,
            "meta": {
                "timestamp": {
                    "type": float,
                    "description": "epoch timestamp of the event",
                },
                "status": {
                    "type": str,
                    "description": "event status",
                },
                "description": {
                    "type": str,
                    "description": "description or reason for the event",
                },
            },
        },
        "event_count": {
            "type": int,
            "description": "total number of fabric monitoring events that have occurred",
            "write": False,
            "default": 0,
        },
        "max_events": {
            "type": int,
            "description": "maximum number of fabric monitoring events",
            "min": 5,
            "max": 8192,
            "default": 1024,
        },

        # reference attributes only
        "status": {
            "reference": True,
            "type": str,
            "values": ["running", "stopped"],
            "description": "current monitor operational status for provided fabric",
            "default": "unknown",
        },
        "reason": {
            "reference": True,
            "type": str,
            "description": "reason for starting or stopping fabric monitor",
            "default": "",
        },
    }

    @classmethod
    @api_callback("before_delete")
    def before_fabric_delete(cls, filters):
        """ before fabric delete, ensure that fabric monitor is stopped.  This only supports single 
            single delete (no bulk delete).  
        """
        if "fabric" not in filters:
            cls.logger.warn("skipping before delete operation on bulk delete")
            return filters
        f = Fabric.load(fabric=filters["fabric"])
        f.stop_fabric_monitor()
        return filters

    @api_route(path="status", methods=["GET"], swag_ret=["status"], role=Role.USER)
    def get_fabric_status(self):
        """ get current fabric status (running/stopped) """
        try:
            status = "stopped"
            manager_status = AppStatus.check_manager_status()
            for fab in manager_status["fabrics"]:
                if fab["fabric"] == self.fabric:
                    if fab["alive"]:
                        status = "running"
                    break
            # fabric not found within manager status implies it is not running
            return jsonify({"status": status})
        except Exception as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
            abort(500, "failed to send message or invalid manager response") 

    @api_route(path="stop", methods=["POST"], swag_ret=["success"])
    def stop_fabric_monitor(self, reason=""):
        """ stop fabric monitor """
        self.auto_start = False
        self.save()
        try:
            if len(reason) == 0: reason = "API requested stop"
            redis = get_redis()
            data={"fabric":self.fabric, "reason":reason}
            msg = eptMsg(MSG_TYPE.FABRIC_STOP,data=data)
            redis.publish(MANAGER_CTRL_CHANNEL, msg.jsonify())
            return jsonify({"success":True})
        except Exception as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
            abort(500, "failed to send message to redis db")

    @api_route(path="start", methods=["POST"], swag_ret=["success"])
    def start_fabric_monitor(self, reason=""):
        """ start fabric monitor """
        self.auto_start = True
        self.save()
        try:
            if len(reason) == 0: reason = "API requested start"
            redis = get_redis()
            data={"fabric":self.fabric, "reason":reason}
            msg = eptMsg(MSG_TYPE.FABRIC_START,data=data)
            redis.publish(MANAGER_CTRL_CHANNEL, msg.jsonify())
            return jsonify({"success":True})
        except Exception as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
            abort(500, "failed to send message to redis db")

    @api_route(path="verify", methods=["POST"], swag_ret=["success","apic_error","ssh_error"])
    def verify_credentials(self):
        """ verify credentials to access APIC API and switch via SSH """

        ret = {"success": False, "apic_error": "", "ssh_error": ""}
        (success, error) = self.verify_apic_credentials()
        if not success: 
            ret["apic_error"] = error
            ret["ssh_error"] = "not tested"
            return jsonify(ret)
        (success, error) = self.verify_ssh_credentials()
        if not success:
            ret["ssh_error"] = error
            return jsonify(ret)
        ret["success"] = True
        return jsonify(ret)

    def verify_apic_credentials(self):
        """ verify current APIC credentials are valid. 
            Return tuple (success boolean, error description)
        """
        # validate inputs
        app_config = get_app_config()
        if len(self.apic_username) == 0:
            return (False, "no apic username configured")
        if app_config["ACI_APP_MODE"] and len(self.apic_cert) > 0:
            if not os.path.exists(self.apic_cert):
                return (False, "certificate file not found")
        elif len(self.apic_password) == 0:
            return (False, "no apic password configured")

        # attempt to connect to the APIC
        session = aci_utils.get_apic_session(self)
        if session is None:
            return (False, "failed to connect or authenticate to APIC")

        # always close session before returning success
        session.close()
        return (True, "")

    def verify_ssh_credentials(self):
        """ verify current ssh credentials are valid and we can connect to a leaf
            Return tuple (success boolean, error description)
        """
        session = aci_utils.get_apic_session(self)
        if session is None:
            return (False, "failed to connect or authenticate to APIC")
        # use API to get first active leaf to test ssh connectivity 
        fabricNodes = aci_utils.get_class(session, "fabricNode")
        if fabricNodes is None or len(fabricNodes)==0:
            return (False, "unable to get list of nodes in fabric")
        attributes = aci_utils.get_attributes(data=fabricNodes)
        if attributes is None or len(attributes)==0:
            return (False, "unable to parse fabricNodes results")
        reg = "topology/pod-(?P<pod_id>[0-9]+)/node-(?P<node_id>[0-9]+)"
        (pod_id, node_id) = (0,0)
        for a in attributes:
            if a["role"] == "leaf" and a["fabricSt"] == "active":
                r1 = re.search(reg, a["dn"])
                if r1 is None:
                    self.logger.warn("failed to parse leaf dn: %s", a["dn"])
                    continue
                (pod_id, node_id) = (r1.group("pod_id"), r1.group("node_id"))
                break
        if pod_id == 0 or node_id == 0:
            return (False, "no active leaf found within fabric")

        # finally, test ssh connectivity to leaf
        if aci_utils.get_ssh_connection(self, pod_id, node_id, session) is None:
            return (False, "failed to establish ssh connection to leaf %s" % (
                            "topology/pod-%s/node-%s" % (pod_id, node_id))
                    )
        # always close session before returning success
        session.close()
        return (True, "")

    @api_route(path="controllers", methods=["POST"], swag_ret=["success", "error"])
    def get_apic_controllers(self):
        """ Connect to APIC and build list of other active controllers in cluster. At this time, 
            only IPv4 oob and inb mgmt addresses are used with preference given to oob address.
        """
        ret = {"success": False, "error": ""}
        session = aci_utils.get_apic_session(self)
        if session is None: 
            ret["error"] = "unable to connect to apic"
            return jsonify(ret)
        objects = aci_utils.get_class(session, "topSystem")
        if objects is None:
            ret["error"] = "failed to read topSystem"
            return jsonify(ret)
        try:
            controllers = []
            for o in objects:
                attr = o.values()[0]["attributes"]
                if "role" in attr and attr["role"] == "controller":
                    if "state" in attr and attr["state"] == "in-service":
                        if "oobMgmtAddr" in attr and attr["oobMgmtAddr"]!="0.0.0.0":
                            if attr["oobMgmtAddr"] not in controllers:
                                controllers.append(attr["oobMgmtAddr"])
                        if "inbMgmtAddr" in attr and attr["inbMgmtAddr"]!="0.0.0.0":
                            if attr["inbMgmtAddr"] not in controllers:
                                controllers.append(attr["inbMgmtAddr"])
            if len(controllers) == 0:
                ret["error"] = "unable to find any active controllers"
                return jsonify(ret)
            self.controllers = controllers
            if not self.save():
                ret["error"] = "unable to save results to database"
                return jsonify(ret)
        except Exception as e:
            self.logger.debug("Traceback:\n%s", traceback.format_exc())
            abort(500, "unexpected error occurred: %s" % e)
        # successful update
        ret["success"] = True
        return jsonify(ret)

    def add_fabric_event(self, status, description):
        """ add a new status and description to events list """
        logger.debug("add event %s: %s to %s", status, description, self.fabric)
        if not self.exists():
            return False
        self.event_count+=1
        self.events.insert(0, {
            "timestamp": time.time(),
            "status": status,
            "description": description
        })
        self.events = self.events[0: self.max_events]
        if not self.save():
            logger.warn("failed to save fabric event %s:%s", status, description)
            return False
        return True

