
import logging, json, requests, re, time, os, traceback
from flask import jsonify, g, abort, current_app
from ..rest import (Rest, Role, api_register, api_route, api_callback)
from . import utils as aci_utils
from ..utils import (get_app, get_app_config, get_user_data)

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
        status = "unknown"
        processes = get_fabric_processes()
        if self.fabric in processes and len(processes[self.fabric])>0:
            status = "running"
        else:
            status = "stopped"
        return jsonify({"status":status})

    @api_route(path="stop", methods=["POST"], swag_ret=["success", "error"])
    def stop_fabric_monitor(self, reason=""):
        """ stop fabric monitor """
        ret = {"success": False, "error": ""}
        if not stop_fabric(self.fabric, reason, rest=False):
            ret["error"] = "failed to stop fabric"
        else: ret["success"] = True
        return jsonify(ret)

    @api_route(path="start", methods=["POST"], swag_ret=["success", "error"])
    def start_fabric_monitor(self, reason=""):
        """ start fabric monitor """
        ret = {"success": False, "error": ""}
        # ensure fabric is not currently running
        processes = get_fabric_processes()
        if self.fabric in processes and len(processes[self.fabric])>0:
            ret["error"] = "fabric monitor for '%s' is already running" % self.fabric
        # verify credentials
        elif not start_fabric(self.fabric, reason, rest=False):
            ret["error"] = "failed to start fabric monitor"
        else:
            ret["success"] = True
        return jsonify(ret)

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


###############################################################################
#
# fabric functions
#
###############################################################################

def add_fabric_event(fabric, status, description):
    """ add an event to fabric events and rotate as required by max_events 
        return boolean success
    """
    logger.debug("add event %s: %s to %s", status, description, fabric)
    f = Fabric.load(fabric=fabric)
    if not f.exists():
        logger.warn("fabric %s does not exist", fabric)
        return False
    f.event_count+=1
    f.events.insert(0, {
        "timestamp": time.time(),
        "status": status,
        "description": description
    })
    if len(f.events) > f.max_events: f.events = f.events[0:f.max_events]
    if not f.save():
        logger.warn("failed to save fabric event %s:%s", status, description)
        return False
    return True

def start_fabric(fabric, reason="", rest=True):
    """ start a fabric monitor
        return True on success else returns False
    """
    return fabric_action(fabric, "start", reason, rest)

def stop_fabric(fabric, reason="", rest=True):
    """ stop a fabric monitor
        return True on success else returns False
    """
    if len(reason) == 0: reason = "unknown stop reason"
    return fabric_action(fabric, "stop", reason, rest)

def fabric_action(fabric, action, reason="", rest=True):
    """ perform fabric monitor action of start/stop/restart by calling 
        corresponding worker process directly or using rest API to trigger the
        event.

        a little danagerous since relying on triggering bash script...
        return False if error raised from shell, else return True
    """
    if fabric is None or len(fabric)==0:
        logger.error("invalid fabric name: %s", fabric)
        return False

    # if rest action then perform approriate API call to trigger event
    if rest:
        return rest_fabric_action(fabric, action, reason)

    background = True
    status_str = ""
    if action == "stop":
        background = False
        status_str = "Stopping"
        cmd = "--stop %s" % fabric
        logger.info("stoping fabric: %s", cmd)
    elif action == "start":
        background = True
        status_str = "Starting"
        cmd = "--start %s" % fabric
        logger.info("starting fabric: %s", cmd)
    else:
        logger.error("invalid fabric action '%s'", action)
        return False

    if aci_utils.execute_worker(cmd, background=background):
        add_fabric_event(fabric, status_str, reason)
        return True
    else:
        logger.error("failed to execute fabric action %s, %s", action, fabric)
        return False

def rest_fabric_action(fabric, action, reason):
    """ perform POST to localhost for fabric action and return True on success,
        else return False.
            action = "start", "stop"
                * start will use 'restart' API
    """
    logger.debug("perform rest fabric action '%s' fabric '%s'",action,fabric)

    if action not in ["start","stop"]:
        logger.error("invalid fabric action '%s'", action)
        return False
    
    lpass = aci_utils.get_lpass()
    if lpass is None: 
        logger.error("failed to determine local password")
        return False

    app = get_app()
    headers = {"content-type":"application/json"}
    s = requests.Session()
    base_url = app.config.get("PROXY_URL", "http://localhost")
    if "http" not in base_url: base_url = "http://%s" % base_url

    # login as local user and then perform post
    url = "%s/api/users/login" % base_url
    data = {"username":"local", "password":lpass}
    r = s.post(url, verify=False, data=json.dumps(data), headers=headers)
    if r.status_code != 200:
        logger.error("failed local login: %s", r.text)
        return False
    
    # send fabric action post
    url = "%s/api/aci/fabrics/%s/%s" % (base_url, fabric, action)
    data = {"reason": reason}
    r = s.post(url, verify=False, data=json.dumps(data), headers=headers)
    if r.status_code != 200:
        logger.error("failed to perform fabric action: %s", r.text)
        return False

    logger.debug("rest fabric action '%s' fabric '%s': %s",action,fabric,
        r.json())
    return True


def get_fabric_processes():
    """ get dict of fabric to pid mappings for each active fabric monitor.  An
        active fabric monitor is a worker running
            python -m app.models.aci.worker --start <fabric-name>
            ignore:
                python -m app.models.aci.worker --stop <fabric-name>
        returns None on error
    """
    fabrics = {}
    cmd = "ps -eo pid,cmd | egrep python | egrep app.models.aci.worker "
    
    reg = "^[ ]*(?P<pid>[0-9]+)[ ]+.+?--start[ ]+(?P<fabric>[^ ]+)"
    out = aci_utils.run_command(cmd)
    if out is None:
        logger.error("failed to get system pids")
        return None
    for l in out.split("\n"):
        l = l.strip()
        if "egrep" in l: continue
        r1 = re.search(reg, l)
        if r1 is not None:
            pid = int(r1.group("pid"))
            fab = r1.group("fabric")
            if fab not in fabrics: fabrics[fab] = []
            if pid not in fabrics[fab]: fabrics[fab].append(pid)
    logger.debug("current fabric processes: %s", fabrics)
    return fabrics
