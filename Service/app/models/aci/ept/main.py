
from .... import create_app
from ... utils import setup_logger
from .. utils import terminate_process
from . ept_worker import eptWorker
from . ept_manager import eptManager
from multiprocessing import Process

import argparse
import logging
import time
import traceback
import sys

# module level logging
logger = logging.getLogger(__name__)



def execute_all_in_one(worker_count):
    # create three parallel process, 1 manager, n worker, and 1 watcher. If any fail restart all
    # subprocesses. 
    
    def get_processes(worker_count):
        # get AIO processes to execute
        return {
            "manager": Process(target=eptManager("m1").run),
            "watcher": Process(target=eptWorker("w0", role="watcher").run),
            "workers": [
                Process(target=eptWorker("w%s"%(w+1), role="worker").run) \
                for w in xrange(0, worker_count)
            ]
        }

    def start_processes(processes):
        # start each process and record PID
        processes["manager"].start()
        logger.info("started process 'manager' with pid: %s", processes["manager"].pid)
        processes["watcher"].start()
        logger.info("started process 'watcher' with pid: %s", processes["manager"].pid)
        for i, p in enumerate(processes["workers"]): 
            p.start()
            logger.info("started 'worker(%s)' with pid: %s", i+1, p.pid)
    
    processes = get_processes(worker_count)
    try:
        start_processes(processes)
        # continually stop/start all processes
        while True:
            time.sleep(60)
            all_alive = True
            if not processes["manager"].is_alive():
                logger.error("manager no longer alive")
                all_alive = False
            if not processes["watcher"].is_alive():
                logger.error("watcher no longer alive")
                all_alive = False
            for p in processes["workers"]:
                if not p.is_alive():
                    logger.error("one or more workers no longer alive")
                    all_alive = False
            if not all_alive:
                logger.debug("one or more processes are no longer alive, restarting...")
                terminate_process(processes["manager"])
                terminate_process(processes["watcher"])
                for p in processes["workers"]: terminate_process(p)

                # get new process objects and start them
                processes = get_processes(worker_count)
                start_processes(processes)

    except (Exception, SystemExit, KeyboardInterrupt) as e:
        logger.error("Traceback:\n%s", traceback.format_exc())
    finally:
        logger.debug("main exited, killing subprocesses")
        terminate_process(processes["manager"])
        terminate_process(processes["watcher"])
        for p in processes["workers"]: terminate_process(p)

if __name__ == "__main__":

    desc = """ dispatch ept manager or worker """
    parser = argparse.ArgumentParser(description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    parser.add_argument("--all-in-one", dest="aio", action="store_true", 
            help="run AIO(all-in-one) mode")
    parser.add_argument("--worker-count", dest="worker_count", type=int, default=3,
            help="worker count in AIO mode (default 3)")
    parser.add_argument("--id", dest="worker_id", help="unique id for this worker")
    parser.add_argument("--role", dest="role", help="worker role", default="worker",
        choices=["manager", "watcher", "worker"])
    parser.add_argument("--stdout", dest="stdout", action="store_true", help="send logs to stdout")
    args = parser.parse_args()

    # initialize app with initializes rest model required by all objects
    app = create_app("config.py")

    stdout = args.stdout
    if args.aio:
        fname = "allInOne.log"
    else:
        fname="worker_%s" % args.worker_id
    debug_modules = [
        "app.models.aci"
    ]
    setup_logger(logger, fname=fname, stdout=stdout)
    for l in debug_modules:
        setup_logger(logging.getLogger(l), fname=fname, stdout=stdout, thread=True)

    if args.aio:
        execute_all_in_one(args.worker_count)
    else:
        if args.worker_id is None:
            logger.error("worker_id is required")
            sys.exit(1)
        if args.role == "manager": 
            w = eptManager(args.worker_id)
        else:
            w = eptWorker(args.worker_id, role=args.role)
        w.run()
        logger.error("worker %s unexpected ended", w.worker_id)
