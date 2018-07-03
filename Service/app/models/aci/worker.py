"""
    For direct execution, ensure script is run as a library module:
        python -m app.models.aci.worker

    @author agossett@cisco.com
"""

from .. utils import get_app, get_db, setup_logger
import logging, sys, traceback

# module level logging
logger = logging.getLogger(__name__)

def db_is_alive():
    """ perform connection attempt to database 
        return True on success or False on error
    """
    logger.debug("checking if db is alive")
    try:
        db = get_db()
        logger.debug("collection names: %s", db.collection_names())
        logger.debug("database is alive")
        return True
    except Exception as e: pass
    logger.error("failed to connect to database")
    return False

def start_monitor(fabric):
    """ start fabric monitor 
        TODO....
    """
    return False

def stop_monitor(fabric):
    from .fabrics import get_fabric_processes
    from .utils import terminate_pid
    processes = get_fabric_processes() 
    logger.debug("fabric proceses: %s", processes)
    pids = processes.get(fabric, [])
    for p in pids: terminate_pid(p)
    return True

def start_all_monitor(conditional): 
    # start all fabric monitors
    if conditional:
        app = get_app()
        if not app.config.get("AUTO_START_MONITOR", False):
            logger.debug("skipping start all as AUTO_START_MONITOR is disabled")
            return
    return execute_all_monitor("start")

def stop_all_monitor(conditional): 
    # stop all fabric monitors
    if conditional:
        app = get_app()
        if not app.config.get("AUTO_START_MONITOR", False):
            logger.debug("skipping stop all as AUTO_START_MONITOR is disabled")
            return
    return execute_all_monitor("stop")
 
def execute_all_monitor(action):
    # start or stop all monitors via provided via rest interface
    # this function returns once start/stop is triggered in background
    from .fabric import (Fabric, rest_fabric_action)

    if action != "start": action = "stop"
    reason = "%s all fabrics" % action
    all_fabrics = Fabric.read(_filters={})
    if "objects" in all_fabrics and len(all_fabrics["objects"])>0:
        for f in all_fabrics["objects"]:
            logger.debug("starting fabric %s", f["fabric"])
            if not rest_fabric_action(f["fabric"], action, reason):
                logger.warn("failed to %s fabric: %s", action, f)
    return True

def get_args():
    """ get arguments for worker """
    import argparse
    desc = """ 
    standalone worker process for aci fabric functions
    """
    allConditionalHelp = """ execute all_start or all_stop conditionally based 
    on environmental variable AUTO_START_MONITOR
    """
    parser = argparse.ArgumentParser(description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    parser.add_argument("--check_db", action="store_true", dest="check_db",
        help="validate successful database connection")
    parser.add_argument("--start", dest="start", type=str, 
        help="start fabric monitor for specified fabric name")
    parser.add_argument("--stop", dest="stop", type=str,
        help="stop fabric monitor for specified fabric name")
    parser.add_argument("--all_stop", action="store_true", dest="all_stop",
        help="stop all fabric monitors")
    parser.add_argument("--all_start", action="store_true", dest="all_start", 
        help="start all fabric monitors")
    parser.add_argument("--all_conditional", action="store_true",
        dest="all_conditional", help=allConditionalHelp)
    parser.add_argument("--stdout", dest="stdout", action="store_true",
        help="send logger output to stdout")
    args = parser.parse_args()
    return args

if __name__ == "__main__":

    # get args from user
    args = get_args()
    method = None
    method_args = []

    stdout = args.stdout
    fname="worker.log"
    debug_modules = [
        "app.models.aci.nodes",
        "app.models.aci.subscription_ctrl", 
        "app.models.aci.utils",
        "app.models.aci.fabrics",
    ]
    setup_logger(logger,fname=fname,stdout=stdout,quiet=True,thread=True)
    for l in debug_modules:
        setup_logger(logging.getLogger(l), fname=fname, stdout=stdout,
                quiet=True,thread=True)

    if args.check_db: 
        logger.debug("worker request: check_db")
        method = db_is_alive
    elif args.all_start:
        logger.debug("start all fabric monitors")
        method = start_all_monitor
        method_args = [args.all_conditional]
    elif args.all_stop:
        logger.debug("stop all fabric monitors")
        method = stop_all_monitor
        method_args = [args.all_conditional]
    elif args.start is not None:
        logger.debug("start monitor request for fabric: %s" % args.start)
        method = start_monitor
        method_args = [args.start]
    elif args.stop is not None:
        logger.debug("stop monitor request for fabric: %s" % args.stop)
        method = stop_monitor
        method_args = [args.stop]
    else:
        logger.warn("no action provided.  use -h for help")
        sys.exit(1)

    # execute method with required arguments and exit with appropriate exit code
    from ..utils import get_app
    app = get_app()
    with app.app_context():
        try:
            if not method(*method_args): sys.exit(1)
            sys.exit(0)
        except Exception as e:
            sys.stderr.write("%s\n"% traceback.format_exc())
    sys.exit(1)

