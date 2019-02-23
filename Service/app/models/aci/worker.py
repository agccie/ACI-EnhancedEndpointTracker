"""
    For direct execution, ensure script is run as a library module:
        python -m app.models.aci.worker

    @author agossett@cisco.com
"""

from .. utils import get_app
from .. utils import get_db
from .. utils import setup_logger
from . utils import clear_endpoint

import logging
import re
import sys
import traceback

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
    parser.add_argument("--stdout", dest="stdout", action="store_true",
        help="send logger output to stdout")
    subparsers = parser.add_subparsers(title="worker options", dest="worker_op")
    parser0 = subparsers.add_parser("check_db", help="validate successful database connection")
    parser1 = subparsers.add_parser("clear", help="clear endpoint in fabric")
    parser1.add_argument("--fabric", required=True, dest="fabric", help="fabric name")
    parser1.add_argument("--pod", required=True, type=int, dest="pod", help="pod id")
    parser1.add_argument("--node", required=True, type=int, dest="node", help="node id")
    parser1.add_argument("--addr", required=True, dest="addr", help="mac, ipv4, or ipv6 address")
    parser1.add_argument("--addr_type", dest="addr_type", help="address type (ip or mac)",
            choices=["mac","ip"])
    parser1.add_argument("--vnid", required=True, type=int, dest="vnid", help="vrf/bd vnid")
    parser1.add_argument("--vrf_name", dest="vrf_name", help="vrf name", default="")
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
        "app.models.aci.utils",
        #"app.models.aci.tools.connection",
    ]
    setup_logger(logger,fname=fname,stdout=stdout,quiet=True,thread=True)
    for l in debug_modules:
        setup_logger(logging.getLogger(l), fname=fname, stdout=stdout,
                quiet=True,thread=True)

    if args.worker_op == "check_db":
        logger.debug("worker request: check_db")
        method = db_is_alive
    elif args.worker_op == "clear":
        logger.debug("worker request: clear endpoint")
        method = clear_endpoint
        method_args = [args.fabric, args.pod, args.node, args.vnid, args.addr, 
                args.addr_type, args.vrf_name]
    else:
        logger.warn("no action provided. use -h for help")
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

