
import logging, json, requests, re, time
from flask import jsonify, g, abort, current_app
from ..rest import (Rest, api_register)
from . import utils as aci_utils
from ..utils import (get_app, get_user_data)

# module level logging
logger = logging.getLogger(__name__)

def verify_credentials(fabric, internal=False):
    """ check that current APIC credentials are valid.  set internal flag to 
        True to return original dict instead of Flask json response
        returns:
            success: boolean,
            apic_error: str,
            switch_error: str
    """
    import os, re
    if not g.user.is_authenticated: abort(401, "Unauthorized")

    session = None
    ret = {
        "apic_error": "Not tested",
        "switch_error": "Not tested",
        "success": False,
    }
    def fail(apic="", switch=""):
        if len(apic)>0: ret["apic_error"] = apic
        if len(switch)>0: ret["switch_error"] = switch
        if session is not None: session.close()
        if internal: return ret
        else: return jsonify(ret)

    # verify valid configuration in settings
    fab = Fabrics.load(fabric=fabric)
    if not fab.exists(): return fail(apic="Fabric %s not found" % fabric)
    if current_app.config["ACI_APP_MODE"] and len(fab.apic_cert)>0:
        if not os.path.exists(fab.apic_cert):
            return fail(apic="Certificate file not found")
    elif len(fab.apic_password) == 0:
        # password requried in non-cert mode
        return fail(apic="No apic password configured")
    if len(fab.apic_username)==0:
        return fail(apic="No apic username configured")

    # connect to the APIC
    session = aci_utils.get_apic_session(fabric)
    if session is None: return fail(apic="Failed to connect to APIC")
    ret["apic_error"] = ""

    # attempt ssh connection to first leaf found in fabricNode
    fabricNodes = aci_utils.get_class(session, "fabricNode")
    if fabricNodes is None or len(fabricNodes)==0:
        return fail(switch="unable to get list of nodes in fabric")
    attributes = aci_utils.get_attributes(data=fabricNodes)
    if attributes is None or len(attributes)==0:
        return fail(switch="unable to parse fabricNodes results")
    reg = "topology/pod-(?P<pod_id>[0-9]+)/node-(?P<node_id>[0-9]+)"
    (pod_id, node_id) = (0,0)
    for a in attributes:
        if a["role"] == "leaf" and a["fabricSt"] == "active":
            r1 = re.search(reg, a["dn"])
            if r1 is None:
                logger.warn("failed to parse leaf dn: %s", a["dn"])
                continue
            (pod_id, node_id) = (r1.group("pod_id"), r1.group("node_id"))
            break
    if pod_id == 0 or node_id == 0:
        return fail(switch="no active leaf found within fabric")
    if aci_utils.get_ssh_connection(fab, pod_id, node_id, session) is None:
        return fail(switch="failed to establish ssh connection to leaf %s" % (
                        "topology/pod-%s/node-%s" % (pod_id, node_id)))
    ret["switch_error"] = ""

    if session is not None: session.close()
    ret["success"] = True
    if internal: return ret
    else: return jsonify(ret)

def update_apic_controllers(fabric):
    """ connect to apic and get list of other active controllers in cluster and
        add them to fabric settings cluster_ips.  For simplicity, will add only
        IPv4 oob and inb mgmt addresses (if not 0) with preference for oob.

        returns:
            success: boolean,
            error: str
    """
    ret = {"error": "Not tested","success": False}
    def fail(msg=""):
        if len(msg)>0: ret["error"] = msg
        return jsonify(ret)
        
    f = Fabrics.load(fabric=fabric)
    if not f.exists(): return fail("fabric %s does not exists in db" % fabric)

    session = aci_utils.get_apic_session(fabric)
    if session is None: return fail("unable to connect to apic")
   
    objects = aci_utils.get_class(session, "topSystem")
    if objects is None: return fail("unable to read topSystem")

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
            return fail("unable to find any additional controllers")

        # update database with new controller info
        if f.controllers != controllers:
            f.controllers = controllers
            if not f.save():
                return fail("unable to save result to database")
                
    except Exception as e:
        return fail("unexpected error: %s" % e)

    ret["error"] = ""
    ret["success"] = True
    return jsonify(ret)

def start_monitor(fabric):
    """ start monitor for provided fabric as background task. 
        args:
            reason: str 
        returns:
            success: boolean,
            error: str
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    reason = get_user_data().get("reason", "API fabric start")
    ret = {
        "success": False,
        "error": ""
    }
    # first verify monitor is not currently running
    status = get_fabric_status(fabric, internal=True)
    if status["status"] == "running":
        ret["error"] = "fabric monitor for '%s' is already running" % fabric
        return jsonify(ret)
    js = verify_credentials(fabric, internal=True)
    logger.debug("js -> %s" % js)
    if not js["success"]: 
        ret["error"] = "verify credentails failed (either rest API or ssh)"
        return jsonify(ret)
    if not start_fabric(fabric, reason, rest=False):
        ret["error"] = "failed to start fabric"
        return jsonify(ret)
    ret["success"] = True
    return jsonify(ret)

def stop_monitor(fabric):
    """ stop monitor """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    reason = get_user_data().get("reason", "API fabric stop")

    ret = {
        "success": False,
        "error": ""
    }
    if not stop_fabric(fabric, reason, rest=False):
        ret["error"] = "failed to stop fabric"
        return jsonify(ret)
    ret["success"] = True
    return jsonify(ret)

def get_fabric_status(fabric, internal=False):
    """ get current fabric status (running/stopped). set internal flag to true
        to return original dict instead of Flask json response
        returns:
            status: running|stopped
    """ 
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    fab = Fabrics.load(fabric=fabric)
    if not fab.exists(): abort(404, "fabric '%s' not found" % fabric)

    ret = {"status": "unknown"}
    processes = get_fabric_processes()
    if fabric in processes and len(processes[fabric])>0:
        ret["status"] = "running"
    else:
        ret["status"] = "stopped"
    if internal: return ret
    else: return jsonify(ret)

def before_fabric_delete(filters, **kwargs):
    """ before fabric delete, ensure that fabric monitor is stopped.  This only
        supports single delete (no bulk delete).  
        Trigger delete for all other db dependences
    """
    fabric = kwargs.get("fabric", None)
    if fabric is None:
        logger.warn("skipping before delete operation on bulk delete")
        return filters
    stop_monitor(fabric)

    # delete all dependencies
    # TODO (ep_epgs, ep_history, ep_moves, ep_nodes, ep_stale, ep_tunnels,
    # ep_vnids, ep_vpcs, ep_subnets, ep_offsubnet)
    #Linecards.delete(_filters={"fabric":fabric})
    #Nodes.delete(_filters={"fabric":fabric})
    return filters

@api_register(path="/aci/fabrics")
class Fabrics(Rest):
    """ ACI Fabrics REST class """

    logger = logging.getLogger(__name__)
    # meta data and type that are exposed via read/write 
    META_ACCESS = {
        "before_delete": before_fabric_delete,
        "routes": [
            {
                "path": "verify",
                "keyed_url": True,
                "methods": ["POST"],
                "function": verify_credentials
            },
            {
                "path": "controllers",
                "keyed_url": True,
                "methods": ["POST"],
                "function": update_apic_controllers
            },
            {
                "path": "start",
                "keyed_url": True,
                "methods": ["POST"],
                "function": start_monitor
            },
            {
                "path": "stop",
                "keyed_url": True,
                "methods": ["POST"],
                "function": stop_monitor
            },
            {
                "path": "status",
                "keyed_url": True,
                "methods": ["GET"],
                "function": get_fabric_status
            },
        ]
    }
    META = {
        "fabric":{
            "key": True,
            "type":str, 
            "default":"", 
            "regex":"^[a-zA-Z0-9\-\.:_]{1,64}$",
        },
        "apic_username":{
            "type":str, 
            "default":"admin",
            "regex":"^[a-zA-Z0-9\-_\.@]{1,128}$"
        },
        "apic_password":{
            "type": str, 
            "default": "",
            "read": False,
            "encrypt": True,
        },
        "apic_hostname":{
            "type":str, 
            "default":"",
        },
        "apic_cert": {
            "type":str,
            "default":"",
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
        "email_address":{
            "regex":"(^$|^[a-zA-Z0-9\-_\.@\+]+$)",
            "description": "email address for email notifications",
        },
        "syslog_server":{
            "regex":"(^$|^[^ \\]{1,256}$)",
            "description": "syslog server address or hostname",
        },
        "syslog_port":{
            "type": int,
            "default": 514,
            "min": 1,
            "max": 0xffff,
            "description": "syslog UDP port",
        },
        "notify_move_email":{
            "type": bool,
            "default": False,
            "description": "enable email notifications for move events",
        },
        "notify_stale_email":{
            "type": bool,
            "default": False,
            "description": "enable email notifications for stale events",
        },
        "notify_offsubnet_email":{
            "type": bool,
            "default": False,
            "description": "enable email notifications for offsubnet events",
        },
        "notify_move_syslog": {
            "type": bool,
            "default": False,
            "description": "enable syslog notifications for move events",
        },
        "notify_stale_syslog": {
            "type": bool,
            "default": False,
            "description": "enable syslog notifications for stale events",
        },
        "notify_offsubnet_syslog": {
            "type": bool,
            "default": False,
            "description": "enable syslog notifications for offsubnet events",
        },
        "auto_clear_stale": {
            "type": bool,
            "default": False,
            "description": "auto-remediate stale endpoints",
        },
        "auto_clear_offsubnet": {
            "type": bool,
            "default": False,
            "description": "auto-remediate offsubnet endpoints",
        },
        "analyze_move": {
            "type": bool,
            "default": True,
            "description": "perform move analysis on each endpoint event",
        },
        "analyze_stale": {
            "type": bool,
            "default": True,
            "description": "perform stale analysis on each endpoint event",
        },
        "analyze_offsubnet": {
            "type": bool,
            "default": True,
            "description": "perform offsubnet analysis on each endpoint event",
        },
        "max_ep_events":{
            "type": int,
            "default": 64,
            "min": 1,
            "max": 1024,
            "description": """
            maximum number of records per endpoint per node to keep in endpoint
            history table.
            """,
        },
        "max_workers":{
            "type": int,
            "default": 5,
            "min": 1,
            "max": 128,
            "description": "worker processes for analyzing endpoint events",
        },
        "max_jobs":{
            "type": int,
            "default": 65536,
            "min": 1024,
            "max": 1048576,
            "description": """
            Maximum number of inflight jobs in subscriber module. If exceeded
            the fabric monitor is restarted
            """,
        },
        "max_startup_jobs":{
            "type": int,
            "default": 655360,
            "min": 1024,
            "max": 1048576,
            "description": """
            Maximum number of inflight jobs in subscriber module during initial
            startup. It is expected that this value is higher than max_jobs as
            it creates an event for every known endpoint in the fabric.  
            """,
        },
        "trust_subscription":{
            "type": str,
            "default": "auto",
            "values": ["yes", "no", "auto"],
            "description": """
            If subscriptions are unreliable on current switch/APIC version of 
            code, the monitor can be forced into polling mode instead of 
            subscription mode. In this mode, each endpoint event triggers an 
            API query.
            """
        },
        "fabric_warning": {
            "write": False,
            "description": "warning message created/cleared by monitor",
        },

        # dynamically discovered inband/outofband address
        "controllers": {
            "type":list,
            "subtype": str,
            "write": False,
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
            "description": "total number of fabric monitoring events that have \
                            occurred",
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
    }


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
    f = Fabrics.load(fabric=fabric)
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
