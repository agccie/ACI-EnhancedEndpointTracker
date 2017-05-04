"""
    EPT Utils
    @author agossett@cisco.com
"""

import logging, logging.handlers, json, re, time, dateutil.parser, datetime
import subprocess, os, signal, sys, traceback
try: import cPickle as pickle
except ImportError: import pickle
from pymongo import UpdateOne, InsertOne
from pymongo.errors import BulkWriteError

# globals
_g_app = None       # track app so we don't need to create it multiple times
_g_jobs = {}        # active jobs indexed by queue and key

# static queue thresholds and timeouts
SESSION_MAX_TIMEOUT             = 91    # apic timeout hardcoded to 90...
SUBSCRIBER_QUEUE_MAX_THRESHOLD  = 32768
MAX_BULK_SIZE                   = 8192  # maximum entries in bulk before insert

# static return codes
RC_SIMULATOR_CLOSE              = 1
RC_SUBSCRIPTION_CLOSE           = 2
RC_SUBSCRIPTION_RESTART         = 3
RC_SUBSCRIPTION_FAIL            = 4

def get_app():
    # returns current app 
    from ... import create_app
    global _g_app
    if _g_app is None:
        _g_app = create_app("config.py")
    return _g_app

# always setup app before initialization
get_app()

# simulation variables 
SIMULATION_MODE = _g_app.config["SIMULATION_MODE"]
SIMULATOR = None
CONNECTION_SIMULATOR = None

###############################################################################
#
# common logging setup
#
###############################################################################

def setup_logger(logger, fname="utils.log", quiet=False):
    """ setup logger with appropriate logging level and rotate options """

    # quiet all other loggers...
    if quiet or SIMULATION_MODE:
        old_logger = logging.getLogger()
        old_logger.setLevel(logging.CRITICAL)
        for h in list(old_logger.handlers): old_logger.removeHandler(h)
        old_logger.addHandler(logging.NullHandler())

    # don't change logger in simulation mode
    if SIMULATION_MODE: return logger
        
    app = get_app()
    logger.setLevel(app.config["LOG_LEVEL"])
    if app.config["LOG_ROTATE"]:
        logger_handler = logging.handlers.RotatingFileHandler(
            "%s/%s"%(app.config["LOG_DIR"],fname),
            maxBytes=app.config["LOG_ROTATE_SIZE"], 
            backupCount=app.config["LOG_ROTATE_COUNT"])
    else:
        logger_handler = logging.FileHandler(
            "%s/%s"%(app.config["LOG_DIR"],fname))
    fmt ="%(process)d||%(asctime)s.%(msecs).03d||%(levelname)s||%(filename)s"
    fmt+=":(%(lineno)d)||%(message)s"
    logger_handler.setFormatter(logging.Formatter(
        fmt=fmt,
        datefmt="%Z %Y-%m-%d %H:%M:%S")
    )
    # remove previous handlers if present
    for h in list(logger.handlers): logger.removeHandler(h)
    logger.addHandler(logger_handler)
    return logger

# setup ept_utils logger
logger = logging.getLogger(__name__)
setup_logger(logger, "utils.log")

###############################################################################
#
# misc/common functions
#
###############################################################################

def pretty_print(js):
    """ try to convert json to pretty-print format """
    try:
        return json.dumps(js, indent=4, separators=(",", ":"))
    except Exception as e:
        return "%s" % js

def parse_timestamp(ts_str):
    """ return float unix timestamp for timestamp string """
    dt = dateutil.parser.parse(ts_str)
    return (time.mktime(dt.timetuple()) + dt.microsecond/1000000.0)

def format_timestamp(timestamp):
    """ format timestamp to datetime string """

    datefmt="%Y %b %d %H:%M:%S %Z"
    try:
        return datetime.datetime.fromtimestamp(int(timestamp)).strftime(datefmt)
    except Exception as e:
        return timestamp

def terminate_process(p):
    """ send SIGTERM and if needed SIGKILL to process.  Note, this receives a
        Process object, not a pid.
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

def ep_is_local(flags):
    # check for 'local' flag within flags and return True if found
    # note, there are other flags that start with 'local' so need to iterate 
    # through each to check specifically for 'local'
    for f in flags.split(","):
        if f == "local": return True
    return False

# pre-compile regex expressions
epm_reg = "node-(?P<node>[0-9]+)/sys/"
epm_reg+= "((ctx-\[vxlan-(?P<vrf>[0-9]+)\]/)|(inst-overlay-1/))"
epm_reg+= "(bd-\[vxlan-(?P<bd>[0-9]+)\]/)?"
epm_reg+= "(vx?lan-\[(?P<encap>vx?lan-[0-9]+)\]/)?"
epm_reg+= "db-ep/"
epm_reg+= "((mac|ip)-\[?(?P<addr>[0-9\.a-fA-F:]+)\]?)?"
epm_rsMacToIp_reg = epm_reg+"/rsmacEpToIpEpAtt-.+?"
epm_rsMacToIp_reg+= "ip-\[(?P<ip>[0-9\.a-fA-F\:]+)\]"
epm_rsMacToIp_reg = re.compile(epm_rsMacToIp_reg)
epm_reg = re.compile(epm_reg)

def parse_epm_event(classname, event, overlay_vnid, ts=None):
    """ parse various epm events and return required attributes 
            dn, node, type, addr, vnid, status, flags, ifId, pcTag, 
            classname, ts
        and optional attributes depending on endpoint type 
            vrf, bd, ip, encap
    """
    attr = {}
    if "imdata" in event:
        for se in event["imdata"]:
            if classname in se and "attributes" in se[classname]:
                attr = se[classname]["attributes"]
                if "_ts" in event: attr["_ts"] = event["_ts"]
    elif classname in event:
        attr = event[classname]["attributes"]
        if "_ts" in event: attr["_ts"] = event["_ts"]
    else:
        logger.debug("failed to parse event %s: %s" % (
            classname, pretty_print(event)))       
        return None
        
    # dn required for every event
    if "dn" not in attr:
        logger.warn("missing(dn) from %s: %s" % (classname, attr))
        return None

    # add ts representing when event was received on server if not present
    if "_ts" not in attr: attr["_ts"] = time.time() if ts is None else ts

    # build vrf/bd/encap/addr=mac/ip fields
    if classname == "epmIpEp" or classname == "epmMacEp":
        r1 = epm_reg.search(attr["dn"])
    elif classname == "epmRsMacEpToIpEpAtt":
        r1 = epm_rsMacToIp_reg.search(attr["dn"])
    else:
        logger.error("invalid/unsupported ep class: %s" % classname)
        return None
    if r1 is None:
        logger.warn("failed to extract vrf/bd/encap from %s dn(%s)" % (
            classname, attr["dn"]))
        return None

    key = {
        "dn": attr["dn"],
        "node": r1.group("node"),
        "type": "mac" if classname == "epmMacEp" else "ip",
        "addr": r1.group("addr"),
        "classname": classname,
        "ts": attr["_ts"]
    }
    for a in ["status", "flags", "ifId", "pcTag"]:
        if a in attr: key[a] = attr[a]
        else: key[a] = ""

    # on refresh, 'status' attribute not present. Default to created
    if len(key["status"])==0: key["status"] = "created"

    for a in ("vrf", "bd", "encap"):
        if r1.group(a) is not None: key[a] = r1.group(a)
    if classname == "epmMacEp":
        key["vnid"] = r1.group("bd")
    else:
        key["vnid"] = r1.group("vrf")
        # handle special case overlay-1 vrf
        if key["vnid"] is None: key["vnid"] = overlay_vnid
        if classname == "epmRsMacEpToIpEpAtt": key["ip"] = r1.group("ip")

    # ensure all returned attributes that are unicode are converted to str 
    for a in key:
        if type(key[a]) is unicode: key[a] = str(key[a])
    return key

def get_ipv4_string(ipv4):
    """ takes 32-bit integer and returns dotted ipv4 """
    return "%s.%s.%s.%s" % (
        (ipv4 & 0xff000000) >> 24,
        (ipv4 & 0xff0000) >> 16,
        (ipv4 & 0xff00) >> 8 ,
        ipv4 & 0xff
    )

ipv4_prefix_reg = "^(?P<o0>[0-9]+)\.(?P<o1>[0-9]+)\.(?P<o2>[0-9]+)\."
ipv4_prefix_reg+= "(?P<o3>[0-9]+)(/(?P<m>[0-9]+))?$"
ipv4_prefix_reg = re.compile(ipv4_prefix_reg)
def get_ipv4_prefix(ipv4):
    """ takes ipv4 string with or without prefix present and returns tuple:
            (address, mask) where addr and mask are 32-bit ints
        if no mask is present, the /32 is assumed
        mask is '1-care' format.  For example:
            /0  = 0x00000000
            /8  = 0xff000000
            /16 = 0xffff0000
            /24 = 0xffffff00
            /32 = 0xffffffff
        returns (None,None) on error
    """
    r1 = ipv4_prefix_reg.search(ipv4)
    if r1 is None:
        logger.warn("address %s is invalid ipv4 address" % ipv4)
        return (None, None)
    if r1.group("m") is not None: mask = int(r1.group("m"))
    else: mask = 32
    oct0 = int(r1.group("o0"))
    oct1 = int(r1.group("o1"))
    oct2 = int(r1.group("o2"))
    oct3 = int(r1.group("o3"))
    if oct0 > 255 or oct1 > 255 or oct2 > 255 or oct3 > 255 or mask > 32:
        logger.warn("address %s is invalid ipv4 address" % ipv4)
        return (None, None)

    addr = (oct0 << 24) + (oct1 << 16) + (oct2 << 8) + oct3
    mask = (~(pow(2,32-mask)-1)) & 0xffffffff
    return (addr&mask, mask)
    
def get_ipv6_string(ipv6):
    """ takes 64-bit integer and converts to ipv6 """
    s = "%x:%x:%x:%x:%x:%x:%x:%x" % (
        (ipv6 & 0xffff0000000000000000000000000000 ) >> 112,
        (ipv6 & 0x0000ffff000000000000000000000000 ) >> 96,
        (ipv6 & 0x00000000ffff00000000000000000000 ) >> 80,
        (ipv6 & 0x000000000000ffff0000000000000000 ) >> 64,
        (ipv6 & 0x0000000000000000ffff000000000000 ) >> 48,
        (ipv6 & 0x00000000000000000000ffff00000000 ) >> 32,
        (ipv6 & 0x000000000000000000000000ffff0000 ) >> 16,
        (ipv6 & 0x0000000000000000000000000000ffff )
    )
    # ipv6 best practice to replaces multiple 0-octects with ::
    return re.sub(":[0:]+", "::", s, 1)

ipv6_prefix_reg = re.compile("^(?P<addr>[0-9a-f:]{2,40})(/(?P<m>[0-9]+))?$",
                            re.IGNORECASE)
def get_ipv6_prefix(ipv6):
    """ takes ipv6 string with or without prefix present and returns tuple:
            (address, mask) where addr and mask are 128-bit ints
        if no mask is present, the /128 is assumed
        mask is '1-care' format.  For example:
            /0  = 0x00000000 00000000 00000000 00000000
            /24 = 0xffffff00 00000000 00000000 00000000
            /64 = 0xffffffff ffffffff 00000000 00000000
            /128= 0xffffffff ffffffff ffffffff ffffffff
        returns (None,None) on error
    """
    r1 = ipv6_prefix_reg.search(ipv6)
    if r1 is None:
        logger.warn("address %s is invalid ipv6 address" % ipv6)
        return (None, None)
    if r1.group("m") is not None: mask = int(r1.group("m"))
    else: mask = 128

    upper = []
    lower = []
    # split on double colon to determine number of double-octects to pad
    dc_split = r1.group("addr").split("::")
    if len(dc_split) == 0 or len(dc_split)>2: 
        logger.warn("address %s is invalid ipv6 address" % ipv6)
        return (None, None)
    if len(dc_split[0])>0:
        for o in dc_split[0].split(":"): upper.append(int(o,16))
    if len(dc_split)==2 and len(dc_split[1])>0:
        for o in dc_split[1].split(":"): lower.append(int(o,16)) 
    # ensure there are <=8 total double-octects including pad
    pad = 8 - len(upper) - len(lower)
    if pad < 0 or pad >8:
        logger.warn("address %s is invalid ipv6 address" % ipv6)
        return (None, None)

    # sum double-octects with shift
    addr = 0
    for n in (upper + [0]*pad + lower): addr = (addr << 16) + n
    mask = (~(pow(2,128-mask)-1)) & 0xffffffffffffffffffffffffffffffff
    return (addr&mask, mask)
    
###############################################################################
#
# database functions
#
###############################################################################

# global used only during rebuild to force push_events to save to memory
# for single bulk update
update_use_bulk = False
update_bulk_entries = {}    # indexed per-database

def push_event(**kwargs):
    """ push event to 'events' list
        set rotate to maximum number of events to keep in entry
        returns True if all operations are successful
    """
    global update_use_bulk
    global update_bulk_entries
    db = kwargs.get("db", None)
    table = kwargs.get("table", None)
    key = kwargs.get("key", None)
    event = kwargs.get("event", None)
    rotate = kwargs.get("rotate", None)         # number of events to limit to
    increment = kwargs.get("increment", None)   # increment a field during push

    # add entry to beginning of events table
    update = {"$push": {
        "events": {"$each":[event], "$position": 0}
    }} 
    if increment is not None:
        update["$inc"] = {increment: 1}
    if rotate is not None:
        update["$push"]["events"]["$slice"] = rotate
    if update_use_bulk:
        if table not in update_bulk_entries: update_bulk_entries[table] = []
        # add update to bulk entries for later commit
        #logger.debug("adding update event to bulk %s:(key:%s) %s" % (
        #    table,key,event))
        update_bulk_entries[table].append(UpdateOne(key,update,upsert=True))
        return True
    else:
        logger.debug("adding event to %s:(key:%s) %s" % (table,key,event))
        r = db[table].update_one(key, update, upsert=True)
        if r.matched_count == 0:
            if "n" in r.raw_result and "updatedExisting" in r.raw_result and \
                r.raw_result["updatedExisting"] is False and \
                r.raw_result["n"]>0:
                # result was upserted (new entry added to db)
                pass
            else:
                logger.warn("failed to insert into table:%s,key:%s,event:%s" % (
                    table, key,event))
                return False
    return True

def bulk_update(table, bulk_updates, **kwargs):
    """ perform bulk_update of updates in provided bulk_updates[table] array 
        and clears bulk_updates[table].
        returns dict with following attributes:
            deleted_count, inserted_count, matched_count, modified_count,
            upserted_count
    """
    app = kwargs.get("app", None)
    ordered = kwargs.get("ordered", False)
    if app is None: app = get_app()
    with app.app_context():
        db = app.mongo.db
        if table in bulk_updates and len(bulk_updates[table])>0:
            logger.debug("performing bulk update to %s of %s events" % (
                table, len(bulk_updates[table])))
            r =db[table].bulk_write(bulk_updates[table],ordered=ordered)
            # clear entries in list
            bulk_updates[table] = []
            return {
                "deleted_count": r.deleted_count,
                "inserted_count": r.inserted_count,
                "matched_count": r.matched_count,
                "modified_count": r.modified_count,
                "upserted_count": r.upserted_count
            }
        else:
            logger.debug("skipping bulk update to %s, 0 events" % table)

    return {
        "deleted_count":0,
        "inserted_count":0,
        "matched_count":0,
        "modified_count":0,
        "upserted_count":0
    }


###############################################################################
#
# REST/connectivity functions
#
###############################################################################

def get_apic_config(fabric):
    # get apic configurations from database along with decrypted password
    # if controllers are present in ep_nodes, return them as well

    from ...models import utils as mutils
    from ...models.ept import EP_Settings
    app = get_app()
    mongo = app.mongo

    ret = None
    with app.app_context():
        ekey = app.config["EKEY"]
        eiv = app.config["EIV"]
        filters = {"fabric": "%s" % fabric}
        results = mutils.filtered_read(mongo.db.ep_settings, 
            su=True, filters=filters, meta=EP_Settings.META)
        if len(results)==1:
            ret = results[0]
            if "apic_password" in ret:
                ret["apic_password"] = mutils.aes_decrypt(
                    ret["apic_password"], ekey=ekey, eiv=eiv)
                if ret["apic_password"] is None: ret["apic_password"] = ""
            if "ssh_password" in ret:
                ret["ssh_password"] = mutils.aes_decrypt(
                    ret["ssh_password"], ekey=ekey, eiv=eiv)
                if ret["ssh_password"] is None: ret["ssh_password"] = ""
            # add controllers to ret
            ret["controllers"] = []
            # in addition to configuration, check if any controllers 
            # present in ep_nodes
            results = mutils.filtered_read(mongo.db.ep_nodes, su=True,
                filters={"role":"controller", "fabric": "%s" % fabric})
            for r in results:
                if "oobMgmtAddr" in r and r["oobMgmtAddr"]!="0.0.0.0":
                    ret["controllers"].append(r["oobMgmtAddr"])
            return ret
        
    # error occurred access database
    return None

def get_apic_session(fabric, subscription_enabled=False):
    """ get_apic_session 
        based on current ep_settings for provided fabric name, connect to
        apic and return valid session object. If fail to connect to apic 
        in setting, try to connect to any other discovered apic within 
        ep_nodes collection

        Returns None on failure
    """

    from ..tools.acitoolkit.acisession import Session
    logger.debug("get_apic_session for fabric: %s" % fabric)
    if SIMULATION_MODE:
        logger.debug("executing in simulation mode")
        return SIMULATOR

    app = get_app()
    hostnames = []
    db_config = get_apic_config(fabric)
    if db_config is None:
        logger.warn("failed to get ep_settings for fabric: %s" % fabric)
        return None

    apic_username = str("%s" % db_config["apic_username"])
    apic_password = str("%s" % db_config["apic_password"])
    apic_cert = ""
    hostnames.append(db_config["apic_hostname"])
    # add all controllers to hostname list for connection attempt
    if not app.config["ACI_APP_MODE"]:
        for c in db_config["controllers"]:
            if c not in hostnames: hostnames.append(c)

    # determine if we should connect with username/password or certificate
    app_cert_mode = False
    if "apic_cert" in db_config and len(db_config["apic_cert"])>0 and \
        app.config["ACI_APP_MODE"]:
        logger.debug("session mode set to app_cert")
        app_cert_mode = True
        apic_cert = str("%s" % db_config["apic_cert"])
        if not os.path.exists(apic_cert):
            logger.warn("quiting app_cert mode, apic_cert file not found: %s"%(
                apic_cert))
            app_cert_mode = False

    # try to create a session with each hostname
    logger.debug("attempting to connect to following apics: %s" % hostnames)
    for h in hostnames:
        # ensure apic_hostname is in url form.  If not, assuming https
        if not re.search("^http", h.lower()):
            h = "https://%s" % h

        # create session object
        logger.debug("attempting to create session on %s@%s" % (
            apic_username, h))
        if app_cert_mode:
            session = Session(h, apic_username, appcenter_user=True, 
                cert_name=apic_username, key=apic_cert,
                subscription_enabled=subscription_enabled)
        else:
            session = Session(h, apic_username, apic_password,
                subscription_enabled=subscription_enabled)
        resp = session.login(timeout=SESSION_MAX_TIMEOUT)
        if resp is not None and resp.ok: 
            logger.debug("successfully connected on %s" % h)
            return session
        else:
            logger.debug("failed to connect on %s" % h)

    logger.warn("failed to connect to any known apic")
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
        logger.debug("host:%s, timeout:%s, get:%s" % (session.ipaddr, 
            timeout,turl))
        tstart = time.time()
        try:
            resp = session.get(turl, timeout=timeout)
        except Exception as e:
            logger.warn("exception occurred in get request: %s" % (
                traceback.format_exc()))
            return None
        logger.debug("response time: %f" % (time.time() - tstart))
        if resp is None or not resp.ok:
            logger.warn("failed to get data: %s" % url)
            return None
        try:
            js = resp.json()
            if "imdata" not in js or "totalCount" not in js:
                logger.error("failed to parse js reply: %s" % pretty_print(js))
                return None
            results+=js["imdata"]
            logger.debug("results count: %s/%s"%(len(results),js["totalCount"]))
            if len(js["imdata"])<page_size or \
                len(results)>=int(js["totalCount"]):
                logger.debug("all pages received")
                return results
            elif (limit is not None and len(js["imdata"]) >= limit):
                logger.debug("limit(%s) hit or exceeded" % limit)
                return results[0:limit]
            page+= 1
        except ValueError as e:
            logger.error("failed to decode resp: %s" % resp.text)
            return None
    return None

def get_dn(session, dn, **kwargs):
    # get a single dn.  Note, with advanced queries this may be list as well
    # therefore, if len(results)>1, then original list is returned
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

def refresh_session(fabric, session=None):
    """ refresh provided sesssion object if it is not longer alive """
    if session is None:
        session = get_apic_session(fabric)
        if session is None:
            logger.warn("failed to get apic session")
            return None
    # perform get request of /uni/ to ensure session is active
    js = get_dn(session, "uni")
    if js is None:
        logger.debug("session no longer alive, manually refreshing")
        session = get_apic_session(fabric)
        if session is None:
            logger.warn("failed to get apic session")
            return None
    return session

def subscribe(fabric, **kwargs):
    """ subscribe
        subscribe to one or more apics for list of interests and callbacks.
        interest: dict{
            "classname": { "callback":func, "all": boolean, "flush":func}
        }
            "callback" - can provide return codes to manage subscription
            "flush"    - can provide return codes to manage subscription
        checker: function to check health of session.  if False is returned
                 then session is considered dead and subscription returns
        checker_interval: inactive period in seconds in which to trigger
                          checker function
        controller: function to control subscription that is checked at 
                    regular interval. controller function needs to return
                    one of the supported return codes
                        RC_SIMULATOR_CLOSE = n/a
                        RC_SUBSCRIPTION_CLOSE = close and exit subscription
                        RC_SUBSCRIPTION_RESTART = restart subscription
                        None = no action
        controller_interval: interval to call controller function
        return codes (int)
            None (error occurred)
            RC_SIMULATOR_CLOSE
            RC_SUBSCRIPTION_CLOSE
    """

    interests = kwargs.get("interests", {})
    checker = kwargs.get("checker", None)
    checker_interval = kwargs.get("checker_interval", 60.0)
    controller = kwargs.get("controller", None)
    controller_interval = kwargs.get("controller_interval", 1.0)
    session = None

    # base_flush method for interests that don't provide a flush method
    def base_flush(events): 
        return restart_fabric(fabric, "queue exceeded max threshold %s" % (
            SUBSCRIBER_QUEUE_MAX_THRESHOLD))
    # base_checker method for subscription w/o one provided
    def base_checker(session): return True
    # base_controller method for subscriptions w/o one provided
    def base_controller(): return
    if checker is None: checker = base_checker
    if controller is None: controller = base_controller
    
    # check each interest for callback
    i_str = ",".join(i for i in interests)
    logger.debug("subscription request for interests: %s" % i_str)
    for i in interests:
        if "callback" not in interests[i]: 
            logger.warn("callback missing for interest: %s" % i)
            return
        if "flush" not in interests[i]:
            interests[i]["flush"] = base_flush
    if len(interests)==0:
        logger.warn("no interests provided for subscription")
        return

    max_restarts = 3
    restart_count = 0
    subscription_success = False
    while restart_count <= max_restarts:
        try: 
            restart_count+=1
            if restart_count>1:     
                logger.debug("%s: restarting in %s sec (count:%s)"% (i_str,
                    5, restart_count))
                time.sleep(5)
                # force session restart
                if session is not None: 
                    session.close()
                    session = None

            # create a new session always
            session = get_apic_session(fabric, subscription_enabled=True)
            if session is None:
                logger.warn("%s: failed to start session" % i_str)
                continue

            # setup each subscription interest
            sub_success = True
            for i in interests:
                url = "/api/class/%s.json?subscription=yes&page-size=100" % i
                interests[i]["url"] = url
                resp = session.subscribe(url, True)
                if resp is None or not resp.ok:
                    logger.warn("%s: subscription failed (%s,%s): %s"%(
                        i_str, session.ipaddr, i, resp))
                    sub_success = False
                    break
                logger.debug("%s: subscription success (%s,%s)" % (
                    i_str, session.ipaddr,i))

            # if any subscription failed to setup, restart
            if not sub_success: continue
            subscription_success = True
            restart_count = 0       # reset restart count on success

            # monitor each subscription with appropriate callback
            heartbeat = time.time()
            controller_heartbeat = time.time()
            while 1:
                interest_found = False
                ts = time.time()
                for i in interests:
                    rc = None
                    url=interests[i]["url"]
                    event_count = session.get_event_count(url)
                    if event_count>SUBSCRIBER_QUEUE_MAX_THRESHOLD:
                        logger.warn("flushing %s events for (%s,%s)" % (
                            event_count, session.ipaddr, i))
                        events = []
                        while session.has_events(interests[i]["url"]):
                            events.append(session.get_event(url))
                        interests[i]["flush"](events)
                        interests_found = True
                    elif event_count>0:
                        e = session.get_event(url)
                        logger.debug("1/%s events sent to (%s,%s)" % (
                            event_count, session.ipaddr, i))
                        interests[i]["callback"](e)
                        interest_found = True

                    # simulator mode returns -1 event_count to signal 
                    # end of simulation
                    if SIMULATION_MODE and event_count<0: 
                        return RC_SIMULATOR_CLOSE

                if not interest_found: 
                    if (ts - heartbeat)>checker_interval:
                        logger.debug("check session(%s) status"%session.ipaddr)
                        if checker(session): heartbeat = ts
                        else:
                            logger.warn("subscription no longer alive")
                            return RC_SUBSCRIPTION_CLOSE
                    # sleep 10 msec and repeat if no data found
                    else: time.sleep(0.01)
                else: heartbeat = ts
                   
                # check controller callback codes if provided
                if (ts - controller_heartbeat) >= controller_interval:
                    controller_heartbeat = ts
                    rc = controller()
                    if rc is not None:
                        if rc == RC_SUBSCRIPTION_CLOSE:
                            logger.debug("ctrl returned SUBSCRIPTION_CLOSE")
                            session.close()
                            return RC_SUBSCRIPTION_CLOSE
                        elif rc == RC_SUBSCRIPTION_RESTART:
                            logger.debug("ctrl returned SUBSCRIPTION_RESTART")
                            session.close()
                            break
        except Exception as e:
            logger.error(traceback.format_exc())
            # no retries on crashes in simulation mode
            if SIMULATION_MODE: return
            else: raise

    if not subscription_success: return RC_SUBSCRIPTION_FAIL

###############################################################################
#
# fabric functions
#
###############################################################################

def fabric_action(fabric, action, reason=""):
    """ call external ./bash/workers script to force app workers to
        stop, start, restart.  
        a little danagerous since relying on triggering bash script...
        return False if error raised from shell, else return True
    """

    # don't perform operations in simulation mode
    if SIMULATION_MODE:
        logger.debug("fabric_action:%s in simulation mode" % action)
        return True

    # get absolute path for top of app
    p = os.path.realpath(__file__)
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    os.chdir(p)
    if fabric is None or len(fabric)==0:
        logger.error("invalid fabric name: %s" % fabric)
        return False
    status_str = ""
    if action == "restart":
        status_str = "Restarting"
        cmd = "/bin/bash ./bash/workers.sh -r %s" % fabric
        logger.info("restarting fabric: %s" % cmd)
    elif action == "stop":
        status_str = "Stopping"
        cmd = "/bin/bash ./bash/workers.sh -k %s" % fabric
        logger.info("stoping fabric: %s" % cmd)
    elif action == "start":
        status_str = "Starting"
        cmd = "/bin/bash ./bash/workers.sh -s %s" % fabric
        logger.info("starting fabric: %s" % cmd)
    else:
        logger.error("invalid fabric action '%s'" % action)
        return False
    try:
        logger.debug("out:\n%s" % subprocess.check_output(cmd, shell=True, 
            stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError as e:
        logger.warn("error executing worker.sh:\n%s" % e)
        logger.warn("stderr:\n%s" % e.output)
        return False

    # add 'ing' to have states: starting, restarting, stopping
    add_fabric_event(fabric, status_str, reason)
    return True

def start_fabric(fabric, reason=""):
    """ start a fabric monitor
        return True on success else returns False
    """
    return fabric_action(fabric, "start", reason)

def restart_fabric(fabric, reason=""):
    """ restart a fabric monitor
        return True on success else returns False
    """
    if len(reason) == 0: reason = "unknown restart reason"
    return fabric_action(fabric, "restart", reason)

def stop_fabric(fabric, reason=""):
    """ stop a fabric monitor
        return True on success else returns False
    """
    if len(reason) == 0: reason = "unknown stop reason"
    return fabric_action(fabric, "stop", reason)

def get_fabric_processes():
    """ get number of processes for each active fabric monitors
        returns dict of fabrics with count of processes active on each
        returns None on error
    """
    fabrics = {}
    cmd = "ps -ef | egrep python | egrep app.tasks.ept.worker "
    try:
        reg = "--fabric (?P<fab>[^ ]+)"
        out = subprocess.check_output(cmd,shell=True,stderr=subprocess.STDOUT)
        for l in out.split("\n"):
            l = l.strip()
            r1 = re.search(reg, l)
            if r1 is not None:
                fab = r1.group("fab")
                if fab not in fabrics: fabrics[fab] = 0
                fabrics[fab]+= 1
    except subprocess.CalledProcessError as e:
        logger.error("failed to get processes:\n%s" % e)
        logger.error("stderr:\n%s" % e.output)
        return None
    return fabrics

def clear_fabric_warning(fabric):
    """ alias for set_fabric_warning with empty string """
    logger.debug("[%s] clearing fabric warning" % fabric)
    return set_fabric_warning(fabric, "")

def set_fabric_warning(fabric, msg):
    """ sets fabric_warning message 
        return boolean success
    """
    app = get_app() 
    if fabric is None:
        logger.error("provided fabric is None")
        return False
    try:
        with app.app_context():
            db = app.mongo.db
            key = {"fabric":fabric}
            # first operation to get max_fabric_events for this fabric
            fab = db.ep_settings.find_one(key)
            if fab is None:
                logger.error("fabric %s not found" % fabric)
                return False
            update = {"$set": {"fabric_warning": msg}}
            logger.debug("[%s] setting fabric_warning: '%s'"%(fabric,msg))
            r = db.ep_settings.update_one(key, update)
            # assume success
            return True
    except Exception as e:
        logger.error("exception occurred\n%s" % traceback.format_exc())
    return False

def add_fabric_event(fabric, status, description, warn=False):
    """ add an event to the fabric settings fabric_events list 
        if warn flag is True, add description to fabric_warning
        return boolean success 
    """

    app = get_app() 
    if fabric is None:
        logger.error("provided fabric is None")
        return False
    try:
        max_fabric_events = 32  # default if not defined
        event = {"ts":time.time(), "status":"%s" % status, 
                    "description":"%s" % description}
        with app.app_context():
            db = app.mongo.db
            key = {"fabric":fabric}
            # first operation to get max_fabric_events for this fabric
            fab = db.ep_settings.find_one(key)
            if fab is None:
                logger.error("fabric %s not found" % fabric)
                return False
            if "max_fabric_events" not in fab:
                logger.warn("max_fabric_events not in %s, defaulting to %s" % (
                    fabric, max_fabric_events))
            else: max_fabric_events = fab["max_fabric_events"]

            # build update and insert into collection
            update = {
                "$push": {
                    "fabric_events": {
                        "$each":[event], "$position": 0, 
                        "$slice": max_fabric_events
                    }
                },
                "$inc": {"fabric_events_count":1},
            } 
            logger.debug("adding event to ep_settings:(key:%s,limit:%s) %s"%(
                key,max_fabric_events,event))
            r = db.ep_settings.update_one(key, update, upsert=True)
            if r.matched_count == 0:
                if "n" in r.raw_result and "updatedExisting" in r.raw_result \
                    and r.raw_result["updatedExisting"] is False and \
                    r.raw_result["n"]>0:
                    # result was upserted (new entry added to db)
                    pass
                else:
                    logger.warn("failed to insert event into ep_settings: %s"%( 
                        event))
                    if warn: return set_fabric_warning(fabric, description)
                    return False
            if warn: return set_fabric_warning(fabric, description)
            return True
    except Exception as e:
        logger.error("exception occurred\n%s" % traceback.format_exc())
    return False

def get_overlay_vnid(session):
    # get fabric overlay-1 vrf vnid

    dn = "uni/tn-infra/ctx-overlay-1"
    r = get_dn(session, dn)
    if r is not None:
        if "fvCtx" in r and "attributes" in r["fvCtx"]:
            attr = r["fvCtx"]["attributes"]
            if "scope" in attr: 
                overlay_vnid =  attr["scope"]
                logger.debug("%s scope: %s" % (dn, overlay_vnid))   
                return overlay_vnid
        logger.warn("unexpected reply(%s) for dn(%s)" % (r, dn))
    logger.warn("get %s return None" % dn)
    return None

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

def worker_bypass(arg_str):
    """ execute worker_bypass function (-b option for /bash/workers)
        with provided argument string.
        NOTE, ensure arg_str is save before executing function...
    """
    # don't perform operations in simulation mode
    if SIMULATION_MODE:
        logger.debug("worker_bypass:%s in simulation mode" % arg_str)
        return True

    # get absolute path for top of app
    p = os.path.realpath(__file__)
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    p = os.path.abspath(os.path.join(p, os.pardir))
    os.chdir(p)
    cmd = "/bin/bash ./bash/workers.sh -b %s" % arg_str
    try:
        logger.debug("%s:\n%s" % (cmd, subprocess.check_output(cmd, shell=True, 
            stderr=subprocess.STDOUT)))
    except subprocess.CalledProcessError as e:
        logger.warn("error executing worker.sh:\n%s" % e)
        logger.warn("stderr:\n%s" % e.output)
        return False

    # assume success
    return True


###############################################################################
#
# Notification functions
#
###############################################################################

def syslog(**kwargs):
    """ send a syslog message to remote server
        for acceptible facilities see:
            https://docs.python.org/2/library/logging.handlers.html
            15.9.9. SysLogHandler

        severity strings:
            alert (1)
            crit (2)
            debug (7)
            emerg (0)
            err (3)
            info (6)
            notice (5)
            warning (4)
    """ 

    severity= kwargs.get("severity", "info")
    facility= kwargs.get("facility",logging.handlers.SysLogHandler.LOG_LOCAL7) 
    process = kwargs.get("process", "EPT")
    server  = kwargs.get("server", None)
    port    = kwargs.get("port", 514)
    msg     = kwargs.get("msg", None)

    if msg is None:
        logger.error("unable to send syslog: no message provided")
        return False
    if server is None:
        logger.error("unable to send syslog: no server provided")
        return False
    try: 
        if(isinstance(port, int)):
            port = int(port)
        else:
            port = 514
    except ValueError as e:
        logger.error("unable to send syslog: invalid port number '%s'"%port)
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
    remote_syslog = logging.handlers.SysLogHandler(
        address = (server,port), 
        facility=facility,
    )
    remote_syslog.setFormatter(logging.Formatter(
        fmt=fmt,
        datefmt=": %Y %b %d %H:%M:%S %Z:")
    )
    syslogger.addHandler(remote_syslog)

    # send syslog (only supporting native python priorities)
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
    method(s)

    # remove syslogger from handler and restore old loggers
    syslogger.removeHandler(remote_syslog)
    for h in old_handlers: logger.addHandler(h)

    # return success
    return True

def email(**kwargs):
    """ send an email """

    app = get_app()
    _to = kwargs.get("to", None)
    _from = kwargs.get("sender", app.config["EMAIL_SENDER"])
    subj = kwargs.get("subject", "subject").replace("\"", "\\\"")
    msg = kwargs.get("msg", "")

    if _to is None:
        raise Exception("\"to\" is a required field")
    cmd = ["mail", "-s", subj]
    if _from is not None and len(_from)>0:
        cmd+= ["-r", _from]
    cmd.append(_to)

    try:
        logging.debug("send mail: (%s), msg: %s" % (cmd,msg))
        ps = subprocess.Popen(("echo", msg), stdout=subprocess.PIPE)
        output = subprocess.check_output(cmd, stdin=ps.stdout, 
            stderr=subprocess.STDOUT)
        ps.wait()
        return True
    except subprocess.CalledProcessError as e:
        logging.error("send mail error:\n%s" % e)
        logger.warn("stderr:\n%s" % e.output)
        return False
    except Exception as e:
        logging.error("unknown error occurred: %s" % e)
        return False

