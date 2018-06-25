"""
    ACI App utils
    @author agossett@cisco.com
"""

import logging, logging.handlers, json, re, time, dateutil.parser, datetime
import subprocess, os, signal, sys, traceback, requests
from pymongo import UpdateOne, InsertOne
from pymongo.errors import BulkWriteError
from ..utils import pretty_print, get_app

# module level logging
logger = logging.getLogger(__name__)

# static queue thresholds and timeouts
SESSION_MAX_TIMEOUT = 120   # apic timeout hardcoded to 90...
SESSION_LOGIN_TIMEOUT = 10  # login should be fast

###############################################################################
#
# REST/connectivity functions
#
###############################################################################

def get_lpass():
    """ get local user password for REST calls against local API 
        return string decrypted password on success else return None
    """
    
    from ..settings import Settings
    s = Settings.load(__read_all=True)
    if s.exists() and hasattr(s, "lpass"):
        return s.lpass
    
    logger.error("unable to determine lpass from settings")
    return None

def build_query_filters(**kwargs):
    """
        queryTarget=[children|subtree]
        targetSubtreeClass=[mo-class]
        queryTargetFilter=[filter]
        rspSubtree=[no|children|full]
        rspSubtreeInclude=[attr]
        rspPropInclude=[all|naming-only|config-explicit|config-all|oper]
        orderBy=[attr]
    """
    queryTarget         = kwargs.get("queryTarget", None)
    targetSubtreeClass  = kwargs.get("targetSubtreeClass", None)
    queryTargetFilter   = kwargs.get("queryTargetFilter", None)
    rspSubtree          = kwargs.get("rspSubtree", None)
    rspSubtreeInclude   = kwargs.get("rspSubtreeInclude", None)
    rspPropInclude      = kwargs.get("rspPropInclude", None)
    orderBy             = kwargs.get("orderBy", None)
    opts = ""
    if queryTarget is not None:
        opts+= "&query-target=%s" % queryTarget
    if targetSubtreeClass is not None:
        opts+= "&target-subtree-class=%s" % targetSubtreeClass
    if queryTargetFilter is not None:
        opts+= "&query-target-filter=%s" % queryTargetFilter
    if rspSubtree is not None:
        opts+= "&rsp-subtree=%s" % rspSubtree
    if rspSubtreeInclude is not None:
        opts+= "&rsp-subtree-include=%s" % rspSubtreeInclude
    if rspPropInclude is not None:
        opts+= "&rsp-prop-include=%s" % rspPropInclude
    if orderBy is not None:
        opts+= "&order-by=%s" % orderBy

    if len(opts)>0: opts = "?%s" % opts.strip("&")
    return opts
                
def get(session, url, **kwargs):
    # handle session request and perform basic data validation.  Return
    # None on error

    # default page size handler and timeouts
    page_size = kwargs.get("page_size", 75000)
    timeout = kwargs.get("timeout", SESSION_MAX_TIMEOUT)
    limit = kwargs.get("limit", None)       # max number of returned objects
    page = 0

    url_delim = "?"
    if "?" in url: url_delim="&"
    
    results = []
    # walk through pages until return count is less than page_size 
    while 1:
        turl = "%s%spage-size=%s&page=%s" % (url, url_delim, page_size, page)
        logger.debug("host:%s, timeout:%s, get:%s", session.ipaddr, 
            timeout,turl)
        tstart = time.time()
        try:
            resp = session.get(turl, timeout=timeout)
        except Exception as e:
            logger.warn("exception occurred in get request: %s",
                traceback.format_exc())
            return None
        logger.debug("response time: %f", (time.time() - tstart))
        if resp is None or not resp.ok:
            logger.warn("failed to get data: %s", url)
            return None
        try:
            js = resp.json()
            if "imdata" not in js or "totalCount" not in js:
                logger.warn("failed to parse js reply: %s", pretty_print(js))
                return None
            results+=js["imdata"]
            logger.debug("results count: %s/%s",len(results),js["totalCount"])
            if len(js["imdata"])<page_size or \
                len(results)>=int(js["totalCount"]):
                logger.debug("all pages received")
                return results
            elif (limit is not None and len(js["imdata"]) >= limit):
                logger.debug("limit(%s) hit or exceeded", limit)
                return results[0:limit]
            page+= 1
        except ValueError as e:
            logger.warn("failed to decode resp: %s", resp.text)
            return None
    return None

def get_dn(session, dn, **kwargs):
    # get a single dn.  Note, with advanced queries this may be list as well
    # for now, always return single value
    opts = build_query_filters(**kwargs)
    url = "/api/mo/%s.json%s" % (dn,opts)
    results = get(session, url, **kwargs)
    if results is not None:
        if len(results)>0: return results[0]
        else: return {} # empty non-None object implies valid empty response
    return None
    
def get_class(session, classname, **kwargs):
    # perform class query
    opts = build_query_filters(**kwargs)
    url = "/api/class/%s.json%s" % (classname, opts)
    return get(session, url, **kwargs)
    
def get_parent_dn(dn):
    # return parent dn for provided dn
    t = dn.split("/")
    t.pop()
    return "/".join(t)

def get_attributes(session=None, dn=None, attribute=None, data=None):
    """ get single attribute from a DN.
        This is a relatively common operation to extract just a single value or
        just parse the result and get the attribute list.
    
        if data is provided, then this function assumes a list of objects or
        raw result from APIC query - for both cases, it assumes all objects are
        of the same set and only returns list of attribute objects.  Note,
        if 'attribute' is set then will only return single result of first
        object with attribute.
        
        else, session and dn are required and this function will perform APIC
        query and then return attribute dict.  If 'attribute' is also set, then
        just raw value of the corresponding attribute for that dn is returned

        return None on error or if dn is not found
    """
    if data is None:
        logger.debug("get attributes '%s' for dn '%s'", attribute, dn)
        data = get_dn(session, dn)
        if data is None or type(data) is not dict or len(data)==0:
            logger.debug("return object for %s is None or invalid", dn)
            return

    # handle case raw 'imdata' dict was received
    if type(data) is dict:
        if "imdata" in data: data = data["imdata"]

    # always treat remaining result as list of objects
    ret = []
    if type(data) is not list: data = [data]
    for obj in data:
        if type(obj) is not dict or len(obj)==0:
            logger.debug("unexpected format for obj: %s" % obj)
            continue
        cname = obj.keys()[0]
        if "attributes" not in obj[cname]:
            logger.debug("%s does not contain attributes: %s", cname, obj)
            continue
        if attribute is not None:
            # only ever return first value matched when attribute is set
            if attribute in obj[cname]["attributes"]:
                return obj[cname]["attributes"][attribute]
        else:
            ret.append(obj[cname]["attributes"])

    # if dn was set, then caller assumes get_dn execute and only one result
    # is present, so don't return list.
    if dn is not None and len(ret)==1: return ret[0]
    return ret

def get_apic_session(fabric, subscription_enabled=False):
    """ get_apic_session 
        based on current aci.settings for provided fabric name, connect to
        apic and return valid session object. If fail to connect to apic 
        in setting, try to connect to any other discovered apic within 
        controllers.

        fabric can be a Fabrics object or string for fabric name

        Returns None on failure
    """
    from .fabrics import Fabrics
    from .tools.acitoolkit.acisession import Session
     
    logger.debug("get_apic_session for fabric: %s", fabric)
    if isinstance(fabric, Fabrics): aci = fabric
    else: aci = Fabrics.load(fabric=fabric)
        
    if not aci.exists(): 
        logger.warn("fabric %s not found", fabric)
        return

    # build list of apics for session attempt
    app = get_app()
    hostnames = [aci.apic_hostname]
    if not app.config["ACI_APP_MODE"]:
        for h in aci.controllers:
            if h not in hostnames: hostnames.append(h)

    # determine if we should connect with cert or credentials
    apic_cert_mode = False
    if len(aci.apic_cert)>0 and app.config["ACI_APP_MODE"]:
        logger.debug("session mode set to apic_cert_mode")
        apic_cert_mode = True
        if not os.path.exists(aci.apic_cert):
            logger.warn("quiting app_cert mode, apic_cert file not found: %s",
                aci.apic_cert)
            apic_cert_mode = False

    # try to create a session with each hostname
    logger.debug("attempting to connect to following apics: %s", hostnames)
    for h in hostnames:
        # ensure apic_hostname is in url form.  If not, assuming https
        if not re.search("^http", h.lower()): h = "https://%s" % h

        # create session object
        logger.debug("creating session on %s@%s",aci.apic_username,h)
        if apic_cert_mode:
            session = Session(h, aci.apic_username, appcenter_user=True, 
                cert_name=aci.apic_username, key=aci.apic_cert,
                subscription_enabled=subscription_enabled)
        else:
            session = Session(h, aci.apic_username, aci.apic_password,
                subscription_enabled=subscription_enabled)
        try:
            resp = session.login(timeout=SESSION_LOGIN_TIMEOUT)
            if resp is not None and resp.ok: 
                logger.debug("successfully connected on %s", h)
                return session
            else:
                logger.debug("failed to connect on %s", h)
                session.close()
        except Exception as e:
            logger.warn("session creation exception: %s",e)
            logger.debug(traceback.format_exc())

    logger.warn("failed to connect to any known apic")
    return None   

def get_ssh_connection(fabric, pod_id, node_id, session=None):
    """ create active/logged in ssh connection object for provided fabric name 
        and node-id.  At this time, all ssh connections are via APIC tep of
        selected controller. 
        None returned on error

        fabric can be a Fabrics object or string for fabric name
    """

    from .tools.connection import Connection
    from .fabrics import Fabrics

    if isinstance(fabric, Fabrics): f = fabric
    else: f = Fabrics.load(fabric=fabric)
    if not f.exists():
        logger.warn("unknown fabric: %s", fabric)
        return
    
    # verify credentials are configured
    if len(f.ssh_username)==0 or len(f.ssh_password)==0:
        logger.warn("ssh credentials not configured")
        return

    if session is None:
        # if user did not provide session object then create one
        session = get_apic_session(f)
        if session is None: 
            logger.warn("failed to get apic session")
            return

    # need to determine apic id and corresponding TEP for ssh bind command
    apic_info = get_attributes(session, "info")
    if apic_info is None or "id" not in apic_info or "podId" not in apic_info:
        logger.warn("unable to get topInfo for apic")
        return
    (apic_id, apic_podId) = (apic_info["id"], apic_info["podId"])
    dn = "topology/pod-%s/node-%s/sys" % (apic_podId, apic_id)
    apic_tep = get_attributes(session, dn, "address")
    if apic_tep is None or apic_tep == "0.0.0.0":
        logger.warn("unable to determine APIC TEP for %s" % dn)
        return

    # first get valid ssh connection to spine through apic. Need node TEP
    dn = "topology/pod-%s/node-%s/sys" % (pod_id, node_id)
    tep = get_attributes(session, dn, "address")
    if tep is None or tep == "0.0.0.0":
        logger.warn("unable to determine valid local TEP for %s" % dn)
        return

    # remove http/https and custom ports from hostname
    ssh_hostname = re.sub("^http(s)://","", f.apic_hostname)
    ssh_hostname = re.sub("/.*$", "", ssh_hostname)
    ssh_hostname = re.sub(":[0-9]+$", "", ssh_hostname)
    logger.debug("hostname set from %s to %s", f.apic_hostname, ssh_hostname)
    logger.debug("creating ssh session to %s", ssh_hostname)
    c = Connection(ssh_hostname)
    c.username = f.ssh_username
    c.password = f.ssh_password
    if not c.login():
        logger.warn("failed to login to apic: %s",ssh_hostname)
        return
    logger.debug("ssh session to apic %s complete: %s",ssh_hostname,c.output)

    # request could have been ssh session to apic, check if node_id is for
    # remote switch or local apic
    if apic_id != node_id:
        opts = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
        cmd = "ssh %s -b %s %s" % (opts, apic_tep, tep)
        logger.debug("creating remote ssh session from %s: %s",apic_tep,cmd)
        if not c.remote_login(cmd):
            logger.warn("failed to login to node %s(%s)", node_id, tep)
            return
        logger.debug("ssh session to node %s complete: %s",tep,c.output)
    logger.debug("successfully connected to %s node-%s", f.fabric, node_id)
    return c 

###############################################################################
#
# background/bash functions
#
###############################################################################

def execute_worker(arg_str, background=True):
    """ spawn worker as background process with provided string
        this needs to execute in the root of the package <base>/app/models/aci
        NOTE, ensure arg_str is SAFE BEFORE executing this function...
    """

    # set log directory for stdout and stderr
    app = get_app()
    stdout = "%s/worker.stdout.log" % app.config.get("LOG_DIR", "/home/app/log")
    stderr = "%s/worker.stderr.log" % app.config.get("LOG_DIR", "/home/app/log")
    

    # get absolute path for top of app
    p = os.path.realpath(__file__)
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    os.chdir(p)
    cmd = "python -m app.models.aci.worker %s >%s 2>%s" % (arg_str,
            stdout, stderr)
    if background: cmd = "%s &" % cmd
    try:
        logger.debug("execute worker: %s", cmd)
        os.system(cmd)
    except Exception as e:
        logger.warn("error executing worker:\n%s", e)
        logger.warn("stderr:\n%s", e.output)
        return False

    # assume success
    return True

def terminate_pid(p):
    """ send SIGKILL to process based on integer pid.
        return booelan success
    """
    if type(p) is not int:
        logger.warn("terminate_pid requires int, received %s: %s", type(p),p)
        return False
    try:
        logger.debug("terminate pid %s", p)
        os.kill(p, signal.SIGKILL)
    except OSError as e:
        logger.warn("error executing kill: %s", e)
        return False
    return True

def terminate_process(p):
    """ send SIGTERM and if needed SIGKILL to process.  
        Note, this receives a Process object, not an integer pid.
        return boolean success
    """
    if p.is_alive():
        p.terminate()
        time.sleep(0.01)
        if p.is_alive():
            try:
                logger.debug("sending SIGKILL to pid(%s)" % p.pid)
                os.kill(p.pid, signal.SIGKILL)
            except OSError as e:
                logger.warn("error occurred while sending kill: %s" % e)
                return False
    return True

def run_command(cmd):
    """ use subprocess.check_output to execute command on shell
        return None on error
    """
    logger.debug("run cmd: \"%s\"", cmd)
    try:
        out = subprocess.check_output(cmd,shell=True,stderr=subprocess.STDOUT)
        return out
    except subprocess.CalledProcessError as e:
        logger.warn("error executing command: %s", e)
        logger.warn("stderr:\n%s", e.output)
        return None

def get_file_md5(path):
    """ use md5sum utility to calculate md5 for file at provided path
        return None on error
    """
    logger.debug("calculate md5 for %s", path)
    if not os.path.exists(path):
        logger.debug("%s not found", path)
        return None
    out = run_command("md5sum %s | egrep -o \"^[0-9a-fA-F]+\"" % path)
    if out is None: return None
    # expect 32-bit hex (128-bit number)
    out = out.strip()
    if re.search("^[0-9a-f]{32}$", out, re.IGNORECASE) is not None:
        logger.debug("md5sum: %s", out)
        return out
    logger.warn("unexpected md5sum result: %s, returning None", out)
    return None
    
