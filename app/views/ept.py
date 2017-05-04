
from flask import current_app, Blueprint, render_template
ept = Blueprint("ept", __name__)

from flask import Flask, jsonify, redirect, url_for
from flask import request, make_response, g, abort
from flask_login import (login_required, current_user)

from ..models.utils import (get_user_data, random_str, MSG_403, 
    force_attribute_type, filtered_read, convert_to_list)

from ..models.ept import (EP_Settings, EP_Nodes, EP_Tunnels, EP_History,
    EP_Move, EP_Stale, EP_OffSubnet, EP_VNIDs)
from ..models.roles import Roles

@ept.route("/fabric")
@ept.route("/fabric/")
@login_required
def fabric():
    return render_template("ept/fabric.html")

@ept.route("/")
@login_required
def endpoints():
    return render_template("ept/endpoints.html")

@ept.route("/<string:fabric>/<int:vnid>/<string:addr>", methods=["GET"])
@login_required
def endpoints_single(fabric, vnid, addr):
    return render_template("ept/endpoints.html", user_fabric=fabric, 
        user_vnid=vnid, user_addr=addr)


##############################################################################
# ept function API, imported by api module
##############################################################################

##### POST controls #####

def ept_restart(fabric):
    """ restarts all ept queue processes for fabric by invoking bash script
        (very messy...)
        
        Returns:
            successs(bool): successfully restarted ept workers
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    if g.user.role != Roles.FULL_ADMIN: abort(403)
    from ..tasks.ept import utils as ept_utils
    success = ept_utils.restart_fabric(fabric, reason="User triggered restart")
    if not success: abort(500, "failed to restart fabric")
    return jsonify({"success":True})

def ept_stop(fabric):
    """ stop/kill all ept workers for fabric and clear queues
        
        Returns:
            successs(bool): successfully stopped ept workers
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    if g.user.role != Roles.FULL_ADMIN: abort(403)
    from ..tasks.ept import utils as ept_utils
    success = ept_utils.stop_fabric(fabric, reason="User triggered stop")
    if not success: abort(500, "failed to stop fabric")
    return jsonify({"success":True})

def ept_clear_endpoint(fabric, vnid, addr):
    """ clear a mac or IP endpoint from provided list of nodes
       
        Args:
            fabric(str): fabric name
            vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
            addr(str): endpoint mac address 
            type(str): 'mac' or 'ip' endpoint
            nodes(list): list of nodes to clear endpoint
 
        Returns:
            success(dict): dictionary indexed by each node with following
                           attributes:
                                success(bool): successfully cleared endpoint
                                details(str): string description if not success
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    if g.user.role != Roles.FULL_ADMIN: abort(403)
    data = get_user_data(["nodes", "type"])
    key = {"vnid":vnid, "addr":addr,"type":data["type"]}
    if key["type"]!="mac" and key["type"]!="ip":
        abort(400, "Invalid endpoint type '%s'" % key["type"])
    if type(data["nodes"]) is not list:
        abort(400, "'nodes' must be type list")

    from ..tasks.ept.ep_worker import clear_fabric_endpoint
    nodes = clear_fabric_endpoint(current_app.mongo.db,fabric,key,data["nodes"])
    if nodes is not None:
        ret = {}
        for n in sorted(nodes.keys()): ret[n] = nodes[n]["ret"]
        return jsonify(ret)
    else:
        abort(500, "an error ocurred executing clear command function")

def app_started():
    """ for ACI_APP_MODE, check presence of start flag.  aborts if 
        application is not running in ACI_APP_MODE
    
        Returns:
            started(bool): app successfully started
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    if not current_app.config["ACI_APP_MODE"]:
        abort(400, "application not running in ACI app mode")
    import os
    started = os.path.exists(current_app.config["ACI_STARTED_FILE"])
    return jsonify({"started": started})

def check_fabric_credentials(fabric):
    """ check that current APIC and ssh credentials are successful.

        Args:
            fabric(str): fabric name

        Returns:
            success(dict): dictionary with index of 'apic' and 'ssh' each with
                           following attributes:
                                success(bool): successfully cleared endpoint
                                details(str): string description if not success

    """
    from ..tasks.ept import utils as ept_utils
    from ..tasks.tools.connection import Connection   
    import re, os
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    ret = {
        "apic": {"success":False, "details":"Not tested"},
        "ssh": {"success":False, "details":"Not tested"},
    }
    # get config for fabric
    config = ept_utils.get_apic_config(fabric)
    if config is None:
        ret["apic"]["details"] = "Failed to read config from database"
        ret["ssh"]["details"] = "Failed to read config from database"
        return jsonify(ret)
    # verify config for apic and test connectivity
    apic_cert = False
    session = None
    if current_app.config["ACI_APP_MODE"] and "apic_cert" in config \
        and len(config["apic_cert"])>0:
        apic_cert = True
        if not os.path.exists(config["apic_cert"]):
            ret["apic"]["details"] = "Certificate file not found"
            return jsonify(ret)
        elif "apic_username" not in config or config["apic_username"] is None:
            ret["apic"]["details"] = "Credentials not configured"
            return jsonify(ret)
    if not apic_cert and ("apic_password" not in config or\
        config["apic_password"] is None):
        ret["apic"]["details"] = "Credentials not configured"
        return jsonify(ret)
    session = ept_utils.get_apic_session(fabric)
    if not session or ept_utils.get_dn(session, "uni") is None:
        ret["apic"]["details"] = "Failed to connect to APIC"
        return jsonify(ret)
    else:
        ret["apic"]["success"] = True
        ret["apic"]["details"] = ""
    # verify config for ssh and test connectivity ONLY if successfully 
    # connected via rest-api (we need to get at least one node to access)
    if session:
        # check if ssh username and password are configured
        if "ssh_username" not in config or "ssh_password" not in config or \
            len(config["ssh_username"])==0 or len(config["ssh_password"])==0:
            ret["ssh"]["details"] = "SSH credentials not configured"
            return jsonify(ret)

        # query to get at least one fabric leaf
        qtf='and(eq(topSystem.role,"leaf"),eq(topSystem.state,"in-service"))' 
        js = ept_utils.get_class(session, "topSystem", page_size=1,
            queryTargetFilter=qtf, orderBy="topSystem.id", limit=1)
        if js is None or len(js)==0:
            ret["ssh"]["details"] = "Failed to find in-service leaf to test"
            return jsonify(ret)
        classname = js[0].keys()[0]
        if classname!="topSystem" or "attributes" not in js[0][classname]:
            ret["ssh"]["details"] = "Failed to find in-service leaf to test"
            return jsonify(ret)
        attr = js[0][classname]["attributes"]
        # set various inband/out-of-band/tep address
        addr = {
            "oobMgmtAddr": attr.get("oobMgmtAddr", ""),
            "inbMgmtAddr": attr.get("inbMgmtAddr", ""),
            "address": attr.get("address", "")
        }.get(config["ssh_access_method"], "address")
        addr_desc = {
            "oobMgmtAddr": "Out-of-Band Management Address",
            "inbMgmtAddr": "Inband Management Address",
            "address": "TEP Address via APIC"
        }.get(config["ssh_access_method"], "address")

        if len(addr)==0 or addr == "0.0.0.0" or addr == "::":
            ret["ssh"]["details"] = "Failed to find valid leaf %s %s"%(
                addr_desc, "node-%s"%attr["id"])
            return jsonify(ret)
        proxy_hostname = None
        if config["ssh_access_method"] == "address": 
            proxy_hostname = re.sub("https?://","",config["apic_hostname"])

        if proxy_hostname is not None: c = Connection(proxy_hostname)
        else: c = Connection(addr)
        c.username = config["ssh_username"]
        c.password = config["ssh_password"]
        if not c.login(max_attempts=2, timeout=5):
            ret["ssh"]["details"] = "Failed to ssh to device(%s) %s" % (
                c.hostname, addr_desc)
            return jsonify(ret)
        if proxy_hostname is not None:
            cmd = "ssh -l %s %s" % (config["ssh_username"], addr)
            if not c.remote_login(cmd, max_attempts=2, timeout=5):
                ret["ssh"]["details"] = "Failed to ssh to device(%s) %s"%(
                    addr_desc, addr)
                return jsonify(ret)
        # successfully logged in via ssh
        ret["ssh"]["success"] = True
        ret["ssh"]["details"] = ""

    return jsonify(ret)
 

##### CREATE #####

def create_setting():
    """ create a new fabric ep setting
        Args:
            (see read_setting for attributes) 

        Returns:
            location(str): resource location of new user
            successs(bool): successfully created user
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    if g.user.role != Roles.FULL_ADMIN: abort(403)

    # lazy import for creating location attribute for new resource
    from .api import ept_read_setting
    result = EP_Settings.create()
    if "success" in result and result["success"] and "username" in result:
        result["location"] = url_for("api.ept_read_setting",
            fabric=result["fabric"].lstrip("/"))
    return jsonify(result)

##### READ #####

def read_settings():
    """ read ep settings

        Returns:
            ep_settings(list): list of ep settings objects
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_Settings.read())

def read_setting(fabric):
    """ read ep settings for a single fabric

        Returns:
            fabric(str): unique fabric name

            analyze_stale(bool): analyze events for stale endpoints
            analyze_move(bool): analyze events for endpoint moves
            analyze_offsubnet(bool): analyze events for off-subnet endpoints

            apic_username(str): apic username
            apic_password(str): apic password
            apic_hostname(str): apic hostname
            apic_cert(str): certificate file for apic authentication (app-mode 
                            only)

            auto_clear_stale(bool): automatically clear stale endpoint
            auto_clear_offsubnet(bool): automatically clear offsubnet endpoint

            email_address(str): address for recipient of email notifications

            fabric_events_count(int): number of events that have occurred
            fabric_events(list): list of events that have occurred on fabric 
                where a fabric_event contains:
                    ts(int): timestamp of event
                    status(str): status of the fabric 
                    description(str): description/reason for the event
            fabric_warning(str): warning messages about fabric

            max_ep_events(int): maximum number of endpoint history events
            max_workers(int): number of worker processes per fabric monitor
            max_jobs(int): maximum number of pending jobs (events) to analyze
                           before new jobs are ignored
            max_fabric_events(int): maximum number of rolling events to store
                                    in fabric_events list

            notify_move_email(bool): send email alert for endpoint move 
            notify_move_syslog(bool): send syslog alert for endpoint move
            notfiy_offsubnet_syslog(bool): send syslog alert for off-subnet EP
            notfiy_offsubnet_email(bool): send email alert for off-subnet EP
            notify_stale_email(bool): send email alert for stale endpoint 
            notify_stale_syslog(bool): send syslog alert for stale endpoints

            ssh_username(str): admin-role username for ssh connectivity to leaf
            ssh_password(str): admin-role password for ssh connectivity to leaf
            ssh_access_method(str): access method for ssh connectivity to leaf:
                    options:
                        "oobMgmtAddr": use out-of-band node address
                        "inbMgmtAddr": use inband node address
                        "address": use node TEP address via APIC

            syslog_server(str): syslog server hostname/IP address
            syslog_port(int): destination port for sending syslog messages
            
            trust_subscription(bool): trust all events are complete/received 
                from subscription and no refresh query is required

    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_Settings.read(fabric))

def read_processes_count():
    """ get count of processes running per fabric monitor
        Returns:
            processes(list): list of process counts where each item contains:
                fabric(str): fabric name
                count(int): number of monitor processes running
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    # get process count per fabric (does not pick up 'zero' count)
    from ..tasks.ept import utils as ept_utils
    processes = ept_utils.get_fabric_processes()
    if processes is None: abort(500, "failed to get process count")
    # get all fabrics and process count if not zero
    results = []
    ep_settings = EP_Settings.read()
    for f in ep_settings["ep_settings"]:  
        if f["fabric"] in processes: 
            results.append({"fabric":f["fabric"],
                "count":processes[f["fabric"]]})
        else:
            results.append({"fabric":f["fabric"], "count":0})
    return jsonify({"processes": results})

def read_nodes():
    """ get list of nodes discovered by the fabric

        Returns:
            nodes(list): list of nodes
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_Nodes.read())

def read_tunnels():
    """ get list of tunnels discovered by the fabric

        Returns:
            tunnels(list): list of tunnels
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_Tunnels.read())

def read_history(fabric=None, addr=None, vnid=None, node=None, search=None):
    """ get per node history events

        Returns:
            history(list): list of ep history events
            
            where a history event contains:
                fabric(str): fabric name
                addr(str): endpoint mac or IP address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                node(str): node for this history
                is_stale(bool): endpoint is currently stale
                is_offsubnet(bool): endpoint is learned offsubnet
                events(list): list of last events for endpoint 

            where an endpoint event contains:
                addr(str): endpoint mac or IP address
                bd(str): bridge domain 
                dn(str): distinguished name of endpoint within EPM database
                flags(str): EPM flags
                ifId(str): interface identifierA
                pcTag(str): policy control tag representing endpoint EPG
                remote(str): remote node ID if endpoint is not local
                rw_bd(str): rewrite bridge domain for IP endpoints
                rw_mac(str): rewrite mac address for IP endpoints
                status(str): status 
                vrf(str): VRF vnid
                ts(float): timestamp when monitoring server received event 
                epg_name(str): epg name
                vnid_name(str): vrf name for IP endpoints or BD name for MACs

            Note that endpoint history events are not populated on search
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_History.read(fabric=fabric, addr=addr, vnid=vnid, 
        node=node, search=search))

def read_history_count():
    """ get total ACTIVE mac and IP count from history table for each fabric
        
        Returns:
            history(list): list of per fabric counts

            where a history count object contains:
                fabric(str): fabric name
                ip(int): number of vrf-unique IP's
                mac(int): number of bd-unique mac's
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_History.count())

def read_history_recent(count=None, ep_type=None):
    """ get most recent events from history table sorted by updated time and 
        limited by count

        Returns:
            recent_events(list): list of endpoints events and timestamp
            
            where an endpoint will contain:
                ts(float): timestamp when monitoring server received event 
                fabric(str): fabric name
                node(str): node ID where endpoint is learned
                type(str): 'ip' or 'mac'
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                bd(str): bridge domain 
                dn(str): distinguished name of endpoint within EPM database
                flags(str): EPM flags
                ifId(str): interface identifierA
                pcTag(str): policy control tag representing endpoint EPG
                remote(str): remote node ID if endpoint is not local
                rw_bd(str): rewrite bridge domain for IP endpoints
                rw_mac(str): rewrite mac address for IP endpoints
                status(str): status 
                vrf(str): VRF vnid
                epg_name(str): epg name
                vnid_name(str): vrf name for IP endpoints or BD name for MACs
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_History.recent(count=count, ep_type=ep_type))

def read_moves_top(count=None, ep_type=None):
    """ get top count of EPs with most moves sorted by updated time and 
        limited by count
        
        Returns:
            top_events(list): list of endpoints and move count 
            
            where an endpoint will contain:
                fabric(str): fabric name
                type(str): 'ip' or 'mac'
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                count(int): total number of moves for endpoint
                ts(float): timestamp of last move
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_Move.top(count=count, ep_type=ep_type))

def read_moves_recent(count=None, ep_type=None):
    """ get most recent endpoint move events sorted by updated time and 
        limited by count
        
        Returns:
            recent_events(list): list of endpoints and move timestamp
            
            where an endpoint will contain:
                fabric(str): fabric name
                type(str): 'ip' or 'mac'
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                count(int): total number of moves for endpoint
                ts(float): timestamp of last move
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_Move.recent(count=count, ep_type=ep_type))

def read_moves(fabric=None, addr=None, vnid=None, search=None):
    """ get move events 

        Returns:
            ep_move(list): list of endpoints and corresponding moves
            
            where an endpoint will contain:
                type(str): 'ip' or 'mac'
                fabric(str): fabric name
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                count(int): total number of moves for endpoint
                events(list): list of last move events for endpoint

            where a move event will contain:
                dst(json): move destination
                    encap(str): encapsulation VLAN or VXLAN 
                    flags(str): EPM flags
                    ifId(str): interface identifierA
                    node(str): node ID where endpoint is learned
                    pcTag(str): policy control tag representing endpoint EPG
                    rw_bd(str): rewrite bridge domain for IP endpoints
                    rw_mac(str): rewrite mac address for IP endpoints
                    ts(float): timestamp when monitoring server received event 
                src(json): move source
                    encap(str): encapsulation VLAN or VXLAN 
                    flags(str): EPM flags
                    ifId(str): interface identifierA
                    node(str): node ID where endpoint is learned
                    pcTag(str): policy control tag representing endpoint EPG
                    rw_bd(str): rewrite bridge domain for IP endpoints
                    rw_mac(str): rewrite mac address for IP endpoints

            Note that endpoint moves events are not populated on search
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_Move.read(fabric=fabric, addr=addr, vnid=vnid, 
        search=search))

def read_stale_top(count=None, ep_type=None):
    """ get top count of EPs with most stale events sorted by updated time and 
        limited by count
        
        Returns:
            top_events(list): list of endpoints and event count 
            
            where an endpoint will contain:
                fabric(str): fabric name
                type(str): 'ip' or 'mac'
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                node(str): node-id in which stale event occurred 
                count(int): total number of stale events for endpoint
                ts(float): timestamp of last stale event
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_Stale.top(count=count, ep_type=ep_type))

def read_stale_recent(count=None, ep_type=None):
    """ get most recent stale EP events sorted by updated time and limited by 
        count
        
        Returns:
            recent_events(list): list of recent stale endpoint events
            
            where an endpoint will contain:
                fabric(str): fabric name
                type(str): 'ip' or 'mac'
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                node(str): node-id in which stale event occurred 
                count(int): total number of stale events for endpoint
                ts(float): timestamp of last stale event
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_Stale.recent(count=count, ep_type=ep_type))

def read_stale_current(count=None, ep_type=None):
    """ get current stale EP sorted by updated time and limited by count
        
        Returns:
            current_stale(list): list of current stale endpoints
            
            where an endpoint will contain:
                fabric(str): fabric name
                type(str): 'ip' or 'mac'
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                node(str): node-id in which stale event occurred 
                count(int): total number of stale events for endpoint
                ts(float): timestamp of last event
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_History.current_stale(count=count, ep_type=ep_type))

def read_stale(fabric=None, addr=None, vnid=None, node=None, search=None):
    """ get stale events

        Returns:
            ep_stale(list): list of endpoints and corresponding stale events
            
            where an endpoint will contain:
                type(str): 'ip' or 'mac'
                fabric(str): fabric name
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                node(str): node-id in which stale event occurred 
                count(int): total number of stale events for endpoint
                events(list): list of last stale events for endpoint

            where a move event will contain:
                remote(str): node ID where endpoint is learned
                expected_remote(str): the expected node ID where endpoint
                                      currently resides
                encap(str): encapsulation VLAN or VXLAN 
                flags(str): EPM flags
                ifId(str): interface identifierA
                pcTag(str): policy control tag representing endpoint EPG
                rw_bd(str): rewrite bridge domain for IP endpoints
                rw_mac(str): rewrite mac address for IP endpoints
                ts(float): timestamp when monitoring server received event 
                epg_name(str): epg name
                vnid_name(str): vrf name for IP endpoints or BD name for MACs

            Note that endpoint stale events are not populated on search
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_Stale.read(fabric=fabric, addr=addr, vnid=vnid, 
        node=node, search=search))

def read_offsubnet_top(count=None):
    """ get top count of EPs with most offsubnet events sorted by updated time and 
        limited by count
        
        Returns:
            top_events(list): list of endpoints and event count 
            
            where an endpoint will contain:
                fabric(str): fabric name
                type(str): 'ip' or 'mac' (only 'ip' supported for offsubnet)
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                node(str): node-id in which offsubnet event occurred 
                count(int): total number of offsubnet events for endpoint
                ts(float): timestamp of last offsubnet event
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_OffSubnet.top(count=count))

def read_offsubnet_recent(count=None):
    """ get most recent offsubnet EP events sorted by updated time and limited by 
        count
        
        Returns:
            recent_events(list): list of recent offsubnet endpoint events
            
            where an endpoint will contain:
                fabric(str): fabric name
                type(str): 'ip' or 'mac' (only 'ip' supported for offsubnet)
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                node(str): node-id in which offsubnet event occurred 
                count(int): total number of offsubnet events for endpoint
                ts(float): timestamp of last offsubnet event
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_OffSubnet.recent(count=count))

def read_offsubnet_current(count=None):
    """ get current offsubnet EP sorted by updated time and limited by count
        
        Returns:
            current_offsubnet(list): list of current offsubnet endpoints
            
            where an endpoint will contain:
                fabric(str): fabric name
                type(str): 'ip' or 'mac' (only 'ip' supported for offsubnet)
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                node(str): node-id in which offsubnet event occurred 
                count(int): total number of offsubnet events for endpoint
                ts(float): timestamp of last event
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_History.current_offsubnet(count=count))

def read_offsubnet(fabric=None, addr=None, vnid=None, node=None, search=None):
    """ get offsubnet events

        Returns:
            ep_offsubnet(list): list of endpoints and corresponding offsubnet events
            
            where an endpoint will contain:
                type(str): 'ip' or 'mac' (only 'ip' supported for offsubnet)
                fabric(str): fabric name
                addr(str): endpoint mac or ip address
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                node(str): node-id in which offsubnet event occurred 
                count(int): total number of offsubnet events for endpoint
                events(list): list of last offsubnet events for endpoint

            where a move event will contain:
                remote(str): node ID where endpoint is learned
                encap(str): encapsulation VLAN or VXLAN 
                flags(str): EPM flags
                ifId(str): interface identifierA
                pcTag(str): policy control tag representing endpoint EPG
                rw_bd(str): rewrite bridge domain for IP endpoints
                rw_mac(str): rewrite mac address for IP endpoints
                ts(float): timestamp when monitoring server received event 
                epg_name(str): epg name
                vnid_name(str): vrf name for IP endpoints or BD name for MACs

            Note that endpoint offsubnet events are not populated on search
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_OffSubnet.read(fabric=fabric, addr=addr, vnid=vnid, 
        node=node, search=search))


def read_vnid(fabric=None, vnid=None, name=None, search=None):
    """ get fabric vnids
 
        Returns:
            ep_vnids(list): list of ep_vnid objects
            
            where an endpoint will contain:
                fabric(str): fabric name
                vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
                name(str): name in dn form matching vnid
                pcTag(str): policy control tag for vnid
                encap(str): encapsulation for vnid
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    return jsonify(EP_VNIDs.read(fabric=fabric, vnid=vnid, name=name,
        search=search))

def read_current_state(fabric, vnid, addr):
    """ get current local information for an endpoint. Returns empty list
        if an error occurs that prevents determining current state

        Returns:
            local(list): list of current local entries

        Where each local endpoint contains:
            fabric(str): fabric name
            vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
            addr(str): endpoint mac or ip address
            type(str): 'ip' or 'mac'
            node(str): node-id where endpoint is currently learned
            ifId(str): interface (vpc-id for vpc endpoints)
            encap(str): encapulation where endpoint is currently learned
            pcTag(str): pcTag where endpoint is currently learned
            rw_bd(str): rewrite BD for IP endpoints
            rw_mac(str): rewrite MAC for IP endpoints
            flags(str): EPM flags
            epg_name(str): epg name
            vnid_name(str): vrf name for IP endpoints or BD name for MACs

    """
    from ..tasks.ept.ep_worker import ep_get_local_state
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    key = {"vnid": vnid, "addr": addr}
    ret = {"local": []}
    local = ep_get_local_state(current_app.mongo.db, fabric, key)
    if local is not None:
        ret["local"] = local
    return jsonify(ret)

##### UPDATE #####

def update_settings(fabric):
    """ Update settings attributes for a fabric user. Only users with 'role' 
        admin can update or create fabric settings.

        Args:
            (see read_setting for attributes) 
        Returns:
            success(bool): successfully updated
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    if g.user.role != Roles.FULL_ADMIN: abort(403)
    return jsonify(EP_Settings.update(fabric))

##### DELETE #####

def delete_settings(fabric):
    """ delete fabric setting

        Returns:
            success(bool): fabric setting successfully deleted
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    if g.user.role != Roles.FULL_ADMIN: abort(403)

    # force kill active fabric first
    from ..tasks.ept.worker import stop_fabric
    stop_fabric([fabric])

    return jsonify(EP_Settings.delete(fabric))

def delete_endpoint(fabric, vnid, addr):
    """ delete endpoint events from database

        Returns:
            success(bool): endpoint events successfully deleted
    """
    if not g.user.is_authenticated: abort(401, "Unauthorized")
    if g.user.role != Roles.FULL_ADMIN: abort(403)
    return jsonify(EP_History.delete(fabric, vnid, addr))
