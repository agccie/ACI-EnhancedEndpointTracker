"""
    For direct execution, ensure script is run as a library module:
        python -m app.tasks.ept.worker

    @author agossett@cisco.com
"""
# module level logger
import logging, re, sys, os, subprocess, signal, time, traceback
from . import utils as ept_utils
from . import manager as ept_manager
logger = logging.getLogger(__name__)
ept_utils.setup_logger(logger, quiet=True)

def db_is_alive():
    """ perform connection attempt to database 
        return True on success or False on error
    """
    logger.debug("checking if db is alive")
    app = ept_utils.get_app()
    try:
        with app.app_context():
            db = app.mongo.db
            db.collection_names()
            return True
    except Exception as e: pass
    return False
        
def get_all_fabrics():
    """" database lookup to get name for each fabric """
    logger.debug("getting all current fabrics")
    app = ept_utils.get_app()
    with app.app_context():
        db = app.mongo.db
        fabrics = []
        for f in db.ep_settings.find({}, projection={"fabric":1}):
            fabrics.append(f["fabric"])
        return fabrics
    return None

def validate_fabric(fabrics):
    """ validate one provided fabric(s) exist in local database 
        return True if all provided fabrics are valid else returns False
    """
    if len(fabrics)==0 or fabrics is None:
        logger.debug("no fabric provided to validate")
        return False
    # get all fabrics and ensure that provided fabric actually exists
    all_fabrics = get_all_fabrics()
    if all_fabrics is None:
        logger.error("failed to get list of current fabrics")
        return False
    if len(all_fabrics)==0:
        logger.debug("no fabrics currently configured")
        return False
    for f in fabrics:
        if f not in all_fabrics:
            logger.error("fabric '%s' does not currently exists" % f)
            return False
        else:
            logger.debug("fabric '%s' is valid" % f)
    # no invalid fabrics found
    return True

def restart_fabric(fabrics):
    """ restart one (and only one) fabric as this kicks off manager function
        which runs forever
        if an error occurs, return False else return True
    """
    if len(fabrics)!=1: 
        logger.error("restart requires exactly one fabric argument: %s"%fabrics)
        return False
    fabric = fabrics[0]
    logger.debug("restarting fabric: %s" % fabric)
    if not stop_fabric([fabric]):
        logger.debug("failed to stop fabric %s" % fabric)
        return False
    return start_fabric([fabric])

def add_event(fabrics, status, description):
    """ add an event to one (and only one) fabric
        if an error occurs, return False else return True
    """
    if len(fabrics)!=1: 
        logger.error("add_event requires exactly one fabric argument: %s" % (
            fabrics))
        return False
    fabric = fabrics[0]
    logger.debug("add event to fabric(%s): %s" % (fabric, status))
    return ept_utils.add_fabric_event(fabric, status, description)

def start_fabric(fabrics):
    """ start one (and only one) fabric as this kicks off manager function
        which runs forever
        if an error occurs, return False else return True
    """
    if len(fabrics)!=1: 
        logger.error("start requires exactly one fabric argument: %s" % fabrics)
        return False
    fabric = fabrics[0]
    logger.debug("starting fabric: %s" % fabric)

    # ensure fabric name is a 'safe' name, if not return false
    safe_fabric_name = "^[a-zA-Z0-9\.\-]{1,64}"
    if not re.search(safe_fabric_name, fabric):
        logger.error("fabric %s is unsafe name" % f)
        return False

    # validate fabric before trying to start it
    if not validate_fabric([fabric]):
        logger.debug("can't start unknown fabric: %s" % fabric)
        return False

        
    # check if fabric is already running
    tf = fabric.replace(".", "\.").replace("-","\-")
    pids = get_fabric_pids(tf)
    if len(pids)>0:
        logger.error("fabric %s is already started" % fabric)
        return False

    ept_manager.manager_job(fabric)
    # manager job runs forever - if it dies or returns then an error occurred
    return False

def stop_fabric(fabrics):
    """ stop one or more fabrics by killing processes
        if an error occurs on any fabric, return False else return True
    """
    if len(fabrics)==0:
        logger.debug("no fabric provided, getting list of all fabrics")
        fabrics = get_all_fabrics()
        if fabrics is None:
            logger.error("failed to get list of current fabrics")
            return False
        if len(fabrics)==0:
            logger.debug("no fabrics currently configured")
            return True

    # ensure fabric name is a 'safe' name, if not return false
    safe_fabric_name = "^[a-zA-Z0-9\.\-]{1,64}"
    for f in fabrics:
        if not re.search(safe_fabric_name, f):
            logger.error("fabric %s is unsafe name" % f)
            return False

    # stop each fabric by issuing a SIGTERM followed by SIGKILL
    for f in fabrics:
        logger.debug("stopping fabric %s" % f)
        tf = f.replace(".", "\.").replace("-","\-")

        # send sigterm to current pids monitoring fabric
        pids = get_fabric_pids(tf)
        if pids is None:
            logger.error("failed to get list of fabric pids")
            return False
        logger.debug("sending SIGTERM to %s pids: %s" % (len(pids), pids))
        for pid in pids:
            try: os.kill(pid, signal.SIGTERM)
            except OSError as e:
                logger.debug("error occurred while sending kill: %s" % e)

        # send sigkill for any remaining pids monitoring fabric
        time.sleep(1)
        pids = get_fabric_pids(tf)
        if pids is None:
            logger.error("failed to get list of fabric pids")
            return False
        if len(pids)>0:
            logger.debug("sending SIGKILL to %s pids: %s" % (len(pids), pids))
            for pid in pids:
                try: os.kill(pid, signal.SIGKILL)
                except OSError as e:
                    logger.debug("error occurred while sending kill: %s" % e)
        time.sleep(1)

    # successfully stopped provided fabrics
    return True

def get_fabric_pids(fabric):
    """ get list of currently running pids for provided fabric name 
        this function assumes caller has already ensured a 'safe' fabric name
        (excludes currently running pid from list)
        returns list of pids or None on error
    """
    mypid = os.getpid()
    pids = []
    cmd = "ps -ef | egrep python | egrep app.tasks.ept.worker | "
    cmd+= "egrep \"\-\-fabric %s\" | awk '{print $2}'" % fabric
    try:
        pids = subprocess.check_output(cmd,shell=True,stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.error("failed to get current processes:\n%s" % e)
        logger.error("stderr:\n%s" % e.output)
        return None
    fpids = []
    for pid in pids.split("\n"):
        if len(pid)>0:
            try: fpids.append(int(pid))
            except ValueError as e: logger.error("invalid pid: %s" % pid)
    if mypid in fpids: fpids.remove(mypid)
    return fpids

def clear_endpoint(fabric, nodes, vnid, addr):
    """ clear fabric endpoint on one or more nodes """
    from . import ep_worker
 
    # need to first guess endpoint type based on provided string
    if re.search("^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", addr) is not None:
        addr_type = "mac"
    else: addr_type = "ip"
    # need to convert all nodes and vnid to strings
    key = { "addr": addr, "vnid": "%s" % vnid, "type": addr_type}
    onodes = ["%s" % n for n in nodes]
    try:
        app = ept_utils.get_app()
        with app.app_context():
            db = app.mongo.db       
            ret = ep_worker.clear_fabric_endpoint(db, fabric, key, onodes)
            if ret is None: return False
            for n in ret:
                if "ret" not in ret[n] or "success" not in ret[n]["ret"] \
                    or not ret[n]["ret"]["success"]:  return False
            # all nodes were success
            return True
    except Exception as e:
        logger.error(traceback.format_exc())
    return False  

def get_args():
    """ get arguments for worker """
    import argparse
    desc = """
    start/stop/restart one or more fabric monitors
    """
    parser = argparse.ArgumentParser(description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    parser.add_argument("--get_fabrics", action="store_true",dest="get_fabrics",
        default=[], help="get all configured fabrics")
    parser.add_argument("--fabric", action="store", dest="fabric", nargs="+", 
        default=[], help="fabric name(s)")
    parser.add_argument("--start", action="store_true", dest="start",
        help="start monitors for fabric(s)")
    parser.add_argument("--stop", action="store_true", dest="stop",
        help="stop monitors for fabric(s)")
    parser.add_argument("--restart", action="store_true", dest="restart",
        help="stop monitors for fabric(s)")
    parser.add_argument("--validate", action="store_true", dest="validate",
        help="validate fabric exists (error exit code if invalid)")
    parser.add_argument("--check_db", action="store_true", dest="check_db",
        help="validate successful database connection")
    parser.add_argument("--add_event_status", action="store", 
        dest="add_event_status",
        help="add event status to fabric events table", default=None)
    parser.add_argument("--add_event_description", action="store",
        dest="add_event_description", default="",
        help="when adding an status event to fabric, include more details")
    parser.add_argument("--clear_endpoint", action="store_true",
        help="clear a fabric endpoint")
    parser.add_argument("--vnid", action="store", type=int, default=None,
        dest="vnid")
    parser.add_argument("--addr", action="store", type=str, default=None, 
        dest="addr", help="IPv4, IPv6, or MAC (xx:xx:xx:xx:xx:xx)")
    parser.add_argument("--nodes", action="store", type=int, default=[],
        nargs="+", dest="nodes")
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    
    # get args from user
    args = get_args()
    if args.get_fabrics:
        fabrics = get_all_fabrics()
        if fabrics is None:
            logger.error("failed to get fabrics")
            sys.exit(1)
        for f in fabrics: print f
        sys.exit(0)
    elif args.start: method = start_fabric
    elif args.stop: method = stop_fabric
    elif args.restart: method = restart_fabric
    elif args.validate: method = validate_fabric 
    elif args.check_db: 
        if db_is_alive():
            logger.debug("database is alive")
            sys.exit(0)
        else:
            logger.error("failed to connect to database")
            sys.exit(1)
    elif args.add_event_status is not None:
        if add_event(args.fabric, args.add_event_status, 
            args.add_event_description):
            logger.debug("add event was successful")
            sys.exit(0)
        else:
            logger.debug("add event failed")
            sys.exit(1)
    elif args.clear_endpoint:
        if args.vnid is None or args.addr is None:
            logger.error("vnid and addr required for clear_endpoint")
            sys.exit(1)
        if len(args.nodes)<1:
            logger.error("one or more nodes required for clear_endpoint")
            sys.exit(1)
        if len(args.fabric)!=1:
            logger.error("one fabric required for clear_endpoint")
            sys.exit(1)
        fabric = args.fabric[0]
        if clear_endpoint(fabric, args.nodes, args.vnid, args.addr):
            logger.debug("successfuly cleared endpoint: %s:%s:%s" % (fabric,
                args.vnid, args.addr))
            sys.exit(0)
        else:
            logger.error("failed to clear endpoint: %s:%s:%s" % (fabric, 
                args.vnid, args.addr))
            sys.exit(1)
    else:
        logger.error("no action provided.  use -h for help")
        sys.exit(1)
    ret = method(args.fabric)
    if not ret:
        logger.error("failed to %s fabric: %s"%(method.__name__, args.fabric))
        sys.exit(1)
