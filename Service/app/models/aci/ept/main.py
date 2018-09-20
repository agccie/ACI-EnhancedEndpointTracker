
from ... utils import setup_logger
from . ept_worker import eptWorker
from . ept_manager import eptManager

import argparse
import logging

# module level logging
logger = logging.getLogger(__name__)

if __name__ == "__main__":

    desc = """ dispatch ept manager or worker """
    parser = argparse.ArgumentParser(description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    parser.add_argument("--id", dest="worker_id", required=True, help="unique id for this worker")
    parser.add_argument("--role", dest="role", required=True, help="worker role", default="worker",
        choices=["manager", "worker"])
    parser.add_argument("--stdout", dest="stdout", action="store_true", help="send logs to stdout")
    args = parser.parse_args()

    stdout = args.stdout
    fname="worker_%s" % args.worker_id
    debug_modules = [
        "app.models.aci"
    ]
    setup_logger(logger, fname=fname, stdout=stdout)
    for l in debug_modules:
        setup_logger(logging.getLogger(l), fname=fname, stdout=stdout, thread=True)

    if args.role == "manager": 
        w = eptManager(args.worker_id)
    else:
        w = eptWorker(args.worker_id, role=args.role)
    w.run()
    logger.error("worker %s unexpected ended", w.worker_id)
