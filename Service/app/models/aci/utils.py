"""
    ACI App utils
    @author agossett@cisco.com
"""

from ..utils import get_app
from ..utils import get_app_config
from ..utils import pretty_print

import logging
import logging.handlers
import os
import re
import signal
import subprocess
import time
import traceback

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
        rspSubtreeClass=[mo-class]
        rspSubtreeInclude=[attr]
        rspPropInclude=[all|naming-only|config-explicit|config-all|oper]
        orderBy=[attr]
    """
    queryTarget         = kwargs.get("queryTarget", None)
    targetSubtreeClass  = kwargs.get("targetSubtreeClass", None)
    queryTargetFilter   = kwargs.get("queryTargetFilter", None)
    rspSubtree          = kwargs.get("rspSubtree", None)
    rspSubtreeClass     = kwargs.get("rspSubtreeClass", None)
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
    if rspSubtreeClass is not None:
        opts+= "&rsp-subtree-class=%s" % rspSubtreeClass
    if rspSubtreeInclude is not None:
        opts+= "&rsp-subtree-include=%s" % rspSubtreeInclude
    if rspPropInclude is not None:
        opts+= "&rsp-prop-include=%s" % rspPropInclude
    if orderBy is not None:
        opts+= "&order-by=%s" % orderBy

    if len(opts)>0: opts = "?%s" % opts.strip("&")
    return opts
                
def _get(session, url, timeout=None, limit=None, page_size=75000):
    # handle session request and perform basic data validation.  
    # this module always returns a generator of the results. If there is an error the first item
    # in the iterator (or on the received page) will be None.

    page = 0
    if timeout is None:
        timeout = SESSION_MAX_TIMEOUT

    url_delim = "?"
    if "?" in url: url_delim="&"
    
    count_received = 0
    count_yield = 0
    # walk through pages until return count is less than page_size 
    while True:
        turl = "%s%spage-size=%s&page=%s" % (url, url_delim, page_size, page)
        logger.debug("host:%s, timeout:%s, get:%s", session.hostname, timeout, turl)
        tstart = time.time()
        try:
            resp = session.get(turl, timeout=timeout)
        except Exception as e:
            logger.warn("exception occurred in get request: %s", e)
            yield None
            return
        if resp is None or not resp.ok:
            logger.warn("failed to get data: %s", url)
            yield None
            return
        try:
            js = resp.json()
            if "imdata" not in js or "totalCount" not in js:
                logger.warn("failed to parse js reply: %s", pretty_print(js))
                yield None
                return
            count_received+= len(js["imdata"])
            logger.debug("time: %0.3f, results count: %s/%s", time.time() - tstart, count_received,
                    js["totalCount"])
                
            for obj in js["imdata"]:
                count_yield+=1
                if (limit is not None and count_yield >= limit):
                    logger.debug("limit(%s) hit or exceeded", limit)
                    return
                yield obj

            if len(js["imdata"])<page_size or count_received >= int(js["totalCount"]):
                #logger.debug("all pages received")
                return
            page+= 1
        except ValueError as e:
            logger.warn("failed to decode resp: %s", resp.text)
            yield None
            return
    yield None
    return

def get_dn(session, dn, timeout=None, **kwargs):
    # get a single dn.  Note, with advanced queries this may be list as well
    # for now, always return single value
    opts = build_query_filters(**kwargs)
    url = "/api/mo/%s.json%s" % (dn,opts)
    ret = []
    for obj in _get(session, url, timeout=timeout):
        if obj is None: 
            return None
        ret.append(obj)
    if len(ret)>0: 
        return ret[0]
    else: 
        # empty non-None object implies valid empty response
        return {} 
    
def get_class(session, classname, timeout=None, limit=None, stream=False, **kwargs):
    # perform class query.  If stream is set to true then this will act as an iterator yielding the
    # next result. If the query failed then the first (and only) result of the iterator will be None
    opts = build_query_filters(**kwargs)
    url = "/api/class/%s.json%s" % (classname, opts)
    if stream:
        return _get(session, url, timeout=timeout, limit=limit) 
    ret = []
    for obj in _get(session, url, timeout=timeout, limit=limit):
        if obj is None:
            return None
        ret.append(obj)
    return ret

def get_parent_dn(dn):
    # return parent dn for provided dn
    # note this is not currently aware of complex dn including prefixes or sub dn...
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
        # for children into 'attributes' so caller functions can pick up child nodes as well
        if "children" in obj[cname]:
            obj[cname]["attributes"]["children"] = obj[cname]["children"]
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

def validate_session_role(session):
    """ verify apic session has appropriate roles/permissions for this app
        return tuple (bool success, error string)
    """
    # validate from session that domain 'all' is present and we are running with role 'admin'
    if "all" in session.domains and "admin" in session.domains["all"].read_roles:
        logger.debug("validated security domain 'all' present with 'admin' read")
        return (True, "")
    else:
        err_msg = "insufficent permissions, user '%s' " % session.uid
        err_msg+= "missing required read role 'admin' for security domain 'all'"
        return (False, err_msg)

def get_apic_session(fabric, resubscribe=False):
    """ get_apic_session 
        based on current aci.settings for provided fabric name, connect to
        apic and return valid session object. If fail to connect to apic 
        in setting, try to connect to any other discovered apic within 
        controllers.

        fabric can be a Fabric object or string for fabric name

        set resubscribe to true to auto restart subscriptions (disabled by default)

        Returns None on failure
    """
    from . fabric import Fabric
    from . session import Session
     
    if isinstance(fabric, Fabric): aci = fabric
    else: aci = Fabric.load(fabric=fabric)
    logger.debug("get_apic_session for fabric: %s", aci.fabric)
        
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
        h = re.sub("[/]+$","", h)

        # create session object
        logger.debug("creating session on %s@%s",aci.apic_username,h)
        if apic_cert_mode:
            session = Session(h, aci.apic_username, appcenter_user=True, 
                cert_name=aci.apic_username, key=aci.apic_cert, resubscribe=resubscribe)
        else:
            session = Session(h, aci.apic_username, aci.apic_password, resubscribe=resubscribe)
        try:
            if session.login(timeout=SESSION_LOGIN_TIMEOUT):
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

        fabric can be a Fabric object or string for fabric name
    """

    from .tools.connection import Connection
    from .fabric import Fabric

    if isinstance(fabric, Fabric): f = fabric
    else: f = Fabric.load(fabric=fabric)
    if not f.exists():
        logger.warn("unknown fabric: %s", f.fabric)
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

def get_controller_version(session):
    # return list of controllers and current running version
    r = get_class(session, "firmwareCtrlrRunning")
    ret = []
    reg = "topology/pod-[0-9]+/node-(?P<node>[0-9]+)/"
    if r is not None:
        for obj in r:
            if "firmwareCtrlrRunning" not in obj or \
                "attributes" not in obj["firmwareCtrlrRunning"]:
                logger.warn("invalid firmwareCtrlrRunning object: %s" % obj)
                continue
            attr = obj["firmwareCtrlrRunning"]["attributes"]
            if "dn" not in attr or "type" not in attr and "version" not in attr:
                logger.warn("firmwareCtrlrRunning missing fields: %s" % attr)
                continue
            r1 = re.search(reg, attr["dn"])
            if r1 is None:
                logger.warn("invalid dn firmwareCtrlrRunning: %s"%attr["dn"])
                continue
            # should never happen but let's double check
            if attr["type"]!="controller":
                logger.warn("invalid 'type' for firmwareCtrlrRunning: %s"%attr)
                continue
            ret.append({"node":r1.group("node"), "version": attr["version"]})

    return ret

def parse_apic_version(version):
    # receive string code version and return dict with major, minor, build, and patch
    # for example:  2.3.1f
    #   major: 2
    #   minor: 3
    #   build: 1
    #   patch: f
    # return None if unable to parse version string

    reg ="(?P<M>[0-9]+)[\-\.](?P<m>[0-9]+)[\.\-\(](?P<p>[0-9]+)\.?(?P<pp>[a-z0-9]+)\)?"
    r1 = re.search(reg, version)
    if r1 is None: return None
    return {
        "major": r1.group("M"),
        "minor": r1.group("m"),
        "build": r1.group("p"),
        "patch": r1.group("pp"),
    }

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
    config = get_app_config()
    stdout = "%s/worker.stdout.log" % config.get("LOG_DIR", "/home/app/log")
    stderr = "%s/worker.stderr.log" % config.get("LOG_DIR", "/home/app/log")

    # get absolute path for top of app
    p = os.path.realpath(__file__)
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    os.chdir(p)
    cmd = "python -m app.models.aci.worker %s >%s 2>%s" % (arg_str,stdout, stderr)
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

def map_signal(sig):
    """ return string name and number for provided signal """
    name = {
        signal.SIGHUP: "SIGHUP",
        signal.SIGINT: "SIGINT",
        signal.SIGQUIT: "SIGQUIT",
        signal.SIGABRT: "SIGABRT",
        signal.SIGKILL: "SIGKILL",
        signal.SIGSEGV: "SIGSEGV",
        signal.SIGTERM: "SIGTERM",
    }.get(sig, "")
    return "(%s)%s" % (sig, name)

def register_signal_handlers():
    """ register listener to various signals to trigger a KeyboardInterrupt (SIGINT) which can
        be caught by running processes to gracefull handle cleanups
    """
    def cleanup_shim(sig_number, frame):
        logger.error("exiting due to signal %s", map_signal(sig_number))
        raise KeyboardInterrupt()

    catch_signals = [
        signal.SIGHUP,      # 1
        #signal.SIGINT,     # 2 (this is translated into keyboardInterrupt which can be caught)
        signal.SIGQUIT,     # 3
        signal.SIGABRT,     # 6
        #signal.SIGKILL,    # 9 (note, cannot register listener for sigkill)
        signal.SIGSEGV,     # 11
        signal.SIGTERM      # 15
    ]
    for sig_number in catch_signals:
        logger.debug("registering listener for %s", map_signal(sig_number))
        signal.signal(sig_number, cleanup_shim)

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
        logger.debug("sending SIGTERM to pid(%s)", p.pid)
        p.terminate()
        # give the process a few seconds to stop
        time.sleep(2.0)
        if p.is_alive():
            try:
                logger.debug("sending SIGKILL to pid(%s)",  p.pid)
                os.kill(p.pid, signal.SIGKILL)
            except OSError as e:
                logger.warn("error occurred while sending kill: %s", e)
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
    
###############################################################################
#
# notification functions
#
###############################################################################

def syslog(msg, server="localhost", server_port=514, severity="info", process="EPT", 
        facility=logging.handlers.SysLogHandler.LOG_LOCAL7):
    """ send a syslog message to remote server.  return boolean success
        for acceptible facilities see:
            https://docs.python.org/2/library/logging.handlers.html
            15.9.9. SysLogHandler
    """
    if msg is None:
        logger.error("unable to send syslog: no message provided")
        return False
    if server is None:
        logger.error("unable to send syslog: no server provided")
        return False
    try:
        if(isinstance(server_port, int)):
            port = int(server_port)
        else:
            port = 514
    except ValueError as e:
        logger.error("unable to send syslog: invalid port number %s", port)
        return False

    if isinstance(severity, str): severity = severity.lower()
    severity = {
        "alert"     : logging.handlers.SysLogHandler.LOG_ALERT,
        "crit"      : logging.handlers.SysLogHandler.LOG_CRIT,
        "debug"     : logging.handlers.SysLogHandler.LOG_DEBUG,
        "emerg"     : logging.handlers.SysLogHandler.LOG_EMERG,
        "err"       : logging.handlers.SysLogHandler.LOG_ERR,
        "info"      : logging.handlers.SysLogHandler.LOG_INFO,
        "notice"    : logging.handlers.SysLogHandler.LOG_NOTICE,
        "warning"   : logging.handlers.SysLogHandler.LOG_WARNING,
        0           : logging.handlers.SysLogHandler.LOG_EMERG,
        1           : logging.handlers.SysLogHandler.LOG_ALERT,
        2           : logging.handlers.SysLogHandler.LOG_CRIT,
        3           : logging.handlers.SysLogHandler.LOG_ERR,
        4           : logging.handlers.SysLogHandler.LOG_WARNING,
        5           : logging.handlers.SysLogHandler.LOG_NOTICE,
        6           : logging.handlers.SysLogHandler.LOG_INFO,
        7           : logging.handlers.SysLogHandler.LOG_DEBUG,
    }.get(severity, logging.handlers.SysLogHandler.LOG_INFO)

    facility_name = {
        logging.handlers.SysLogHandler.LOG_AUTH: "LOG_AUTH",
        logging.handlers.SysLogHandler.LOG_AUTHPRIV: "LOG_AUTHPRIV",
        logging.handlers.SysLogHandler.LOG_CRON: "LOG_CRON",
        logging.handlers.SysLogHandler.LOG_DAEMON: "LOG_DAEMON",
        logging.handlers.SysLogHandler.LOG_FTP: "LOG_FTP",
        logging.handlers.SysLogHandler.LOG_KERN: "LOG_KERN",
        logging.handlers.SysLogHandler.LOG_LPR: "LOG_LPR",
        logging.handlers.SysLogHandler.LOG_MAIL: "LOG_MAIL",
        logging.handlers.SysLogHandler.LOG_NEWS: "LOG_NEWS",
        logging.handlers.SysLogHandler.LOG_SYSLOG: "LOG_SYSLOG",
        logging.handlers.SysLogHandler.LOG_USER: "LOG_USER",
        logging.handlers.SysLogHandler.LOG_UUCP: "LOG_UUCP",
        logging.handlers.SysLogHandler.LOG_LOCAL0: "LOG_LOCAL0",
        logging.handlers.SysLogHandler.LOG_LOCAL1: "LOG_LOCAL1",
        logging.handlers.SysLogHandler.LOG_LOCAL2: "LOG_LOCAL2",
        logging.handlers.SysLogHandler.LOG_LOCAL3: "LOG_LOCAL3",
        logging.handlers.SysLogHandler.LOG_LOCAL4: "LOG_LOCAL4",
        logging.handlers.SysLogHandler.LOG_LOCAL5: "LOG_LOCAL5",
        logging.handlers.SysLogHandler.LOG_LOCAL6: "LOG_LOCAL6",
        logging.handlers.SysLogHandler.LOG_LOCAL7: "LOG_LOCAL7",
    }.get(facility, "LOG_LOCAL7")

    # get old handler and save it, but remove from module logger
    old_handlers = []
    for h in list(logger.handlers):
        old_handlers.append(h)
        logger.removeHandler(h)

    # setup logger for syslog
    syslogger = logging.getLogger("syslog")
    syslogger.setLevel(logging.DEBUG)
    fmt = "%(asctime)s %(message)s"
    remote_syslog = logging.handlers.SysLogHandler(address=(server,port),facility=facility)
    remote_syslog.setFormatter(logging.Formatter(fmt=fmt,datefmt=": %Y %b %d %H:%M:%S %Z:"))
    syslogger.addHandler(remote_syslog)

    # send syslog (only supporting native python priorities for now)
    s = "%%%s-%s-%s: %s" % (facility_name, severity, process, msg)
    method = {
        0: syslogger.critical,
        1: syslogger.critical,
        2: syslogger.critical,
        3: syslogger.error,
        4: syslogger.warning,
        5: syslogger.warning,
        6: syslogger.info,
        7: syslogger.debug,
    }.get(severity, syslogger.info)
    logger.debug("sending syslog(%s,%s): %s", server, port, s)
    method(s)
    # remove syslogger from handler and restore old loggers
    syslogger.removeHandler(remote_syslog)
    for h in old_handlers: logger.addHandler(h)
    # return success
    return True

def email(receiver=None, subject=None, msg=None, sender=None):
    """ send an email and return boolean success """
    if receiver is None:
        logger.error("email recipient not specified")
        return False
    # build sendmail command
    if subject is not None: 
        subject = re.sub("\"", "\\\"", subject)
        cmd = ["mail", "-s", subject]
    else:
        cmd = ["mail"]
    if sender is not None and len(sender)>0:
        cmd+= ["-r", sender]

    cmd.append(receiver)
    try:
        logger.debug("send mail: (%s), msg: %s", cmd, msg)
        ps = subprocess.Popen(("echo", msg), stdout=subprocess.PIPE)
        output = subprocess.check_output(cmd, stdin=ps.stdout, stderr=subprocess.STDOUT)
        ps.wait()
        return True
    except subprocess.CalledProcessError as e:
        logger.warn("send mail error:\n%s", e)
        logger.debug("stderr:\n%s", e.output)
        return False
    except Exception as e:
        logger.error("unknown error occurred: %s", e)
        return False

###############################################################################
#
# clear ept endpoint (triggered by worker or via api)
#
###############################################################################

def clear_endpoint(fabric, pod, node, vnid, addr, addr_type="ip", vrf_name=""):
    """ ssh to node id and clear endpoint. fabric can be fabric name or Fabric object. If addr_type
        is a mac, then vnid is remapped to FD vlan before clear is executed.
        return bool success
    """
    from . fabric import Fabric
    from . ept.common import parse_vrf_name
    from . ept.common import get_mac_string
    from . ept.common import get_mac_value
    from . ept.ept_vnid import eptVnid
    if isinstance(fabric, Fabric): f = fabric
    else: f = Fabric.load(fabric=fabric)

    logger.debug("clear endpoint [%s, node:%s, vnid:%s, addr:%s]", f.fabric, node, vnid, addr)
    if not f.exists():
        logger.warn("unknown fabric: %s", f.fabric)
        return False
    session = get_apic_session(f)
    if session is None:
        logger.warn("failed to get apic session for fabric: %s", f.fabric)
        return False
    ssh = get_ssh_connection(f, pod, node, session=session)
    if ssh is None:
        logger.warn("failed to ssh to pod:%s node:%s", pod, node)
        return False

    if addr_type == "ip":
        ctype = "ipv6" if ":" in addr else "ip"
        if len(vrf_name) == 0:
            # try to determine vrf name from eptVnid table
            v = eptVnid.find(fabric=f.fabric, vnid=vnid)
            if len(v) > 0:
                vrf_name = parse_vrf_name(v[0].name)
                if vrf_name is None:
                    logger.warn("failed to parse vrf name from ept vnid_name: %s", v.name)
                    return False
            else:
                logger.warn("failed to determine vnid_name for fabric: %s, vnid: %s",f.fabric,vnid)
                return False
        cmd = "vsh -c 'clear system internal epm endpoint key vrf %s %s %s'" % (vrf_name,ctype,addr)
        if ssh.cmd(cmd) == "prompt":
            logger.debug("successfully cleared endpoint: %s", cmd)
            return True
        else:
            logger.warn("failed to execute clear cmd: %s", cmd)
            return False
    else:
        # first cast mac into correct format
        addr = get_mac_string(get_mac_value(addr),fmt="std")
        
        # to determine mac FD need to first verify mac exists and then use parent dn to query
        # l2BD, vlanCktEp, vxlanCktEp object (good thing here is that we don't care which object 
        # type, each will have id attribute that is the PI vlan)
        # here we have two choices, first is APIC epmMacEp query which hits all nodes or, since ssh
        # session is already up, we can execute directly on the leaf. For that later case, it will
        # be easier to use moquery with grep then parsing json with extra terminal characters...
        cmd = "moquery -c epmMacEp -f 'epm.MacEp.addr==\"%s\"' | egrep '^dn' | egrep 'vxlan-%s'"%(
                addr, vnid)
        if ssh.cmd(cmd) == "prompt":
            r1 = re.search("dn[ ]*:[ ]*(?P<dn>sys/.+)/db-ep", ssh.output)
            if r1 is not None:
                cmd = "moquery -d '%s' | egrep '^id'" % r1.group("dn")
                if ssh.cmd(cmd) == "prompt":
                    r2 = re.search("id[ ]*:[ ]*(?P<pi>[0-9]+)", ssh.output)
                    if r2 is not None:
                        cmd = "vsh -c 'clear system internal epm endpoint key vlan %s mac %s'" % (
                            r2.group("pi"), addr)
                        if ssh.cmd(cmd) == "prompt":
                            logger.debug("successfully cleared endpoint: %s", cmd)
                            return True
                        else:
                            logger.warn("failed to execute clear cmd: %s", cmd)
                            return False
                    else:
                        logger.warn("failed to extract pi-vlan id from %s: %s", r1.group("dn"), 
                            ssh.output)
                        return False
                else:
                    logger.warn("failed to execute command: %s", cmd)
            else:
                logger.debug("failed to parse bd/cktEp from dn or endpoint not found: %s",ssh.output)
                # assume parsing was fine and that endpoint is no longer present (so cleared!)
                return True
        else:
            logger.warn("failed to execute moquery command to determine mac fd on leaf")
            return False
        
