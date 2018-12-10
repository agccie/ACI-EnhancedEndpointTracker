
from .... import create_app
from ... utils import setup_logger
from .. utils import terminate_process
from . ept_worker import eptWorker
from . ept_manager import eptManager
from multiprocessing import Process

import argparse
import logging
import re
import time
import traceback
import sys

# module level logging
logger = logging.getLogger(__name__)

def execute(role="aio", count=1, worker_id=None, restart=False, unique_log=True, debug_modules=[]):
    # execute a manager/worker/watcher or within all-in-one mode with process monitor capability 
    # to restart on failure.
  
    def wrapper(wid, role):
        # wrapper to start a manager/worker sub process with separate logfile if enabled
        if unique_log:
            fname = "%s_%s.log" % (role, wid)
            setup_logger(logger, fname=fname)
            for l in debug_modules:
                setup_logger(logging.getLogger(l), fname=fname, thread=True)
        if role == "manager":
            ept = eptManager(wid)
        else:
            ept = eptWorker(wid, role=role)
        ept.run()

    def get_processes():
        if role == "aio":
            # get AIO processes to execute
            return [
                    Process(target=wrapper, args=("m1","manager",)),
                    Process(target=wrapper, args=("x0", "watcher",))
                ] + [
                    Process(target=wrapper, args=("w%s" % w, "worker",)) \
                    for w in xrange(0, count)
                ]
        elif role == "manager":
            return [ Process(target=wrapper, args=("m%s" % worker_id,"manager",)) ]
        else:
            base = "x" if role == "watcher" else "w"
            base_id = worker_id
            return [
                    Process(target=wrapper, args=("%s%s"%(base, base_id+w), role,)) \
                    for w in xrange(0, count)
                ]

    def start_processes(processes):
        # start each process and record PID
        for i, p in enumerate(processes):
            p.start()
            logger.info("started process %s with pid: %s", i, p.pid)


    processes = get_processes()
    try:
        start_processes(processes)
        # continually stop/start all processes
        while True:
            time.sleep(60)
            all_alive = True
            for i, p in enumerate(processes):
                if not p.is_alive():
                    logger.error("process %s, pid(%s) not longer alive", i, p.pid)
                    all_alive = False
            if not all_alive:
                for p in processes: 
                    terminate_process(p)
                # get new process objects and start them
                if restart:
                    processes = get_processes()
                    start_processes(processes)
                else:
                    return

    except (Exception, SystemExit, KeyboardInterrupt) as e:
        logger.error("Traceback:\n%s", traceback.format_exc())
    finally:
        logger.debug("main exited, killing subprocesses")
        for p in processes: terminate_process(p)

if __name__ == "__main__":

    desc = """ dispatch ept manager or worker """
    parser = argparse.ArgumentParser(description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    parser.add_argument("--all-in-one", dest="aio", action="store_true", 
            help="run AIO(all-in-one) mode")
    parser.add_argument("--count", dest="count", type=int, default=1,
            help="worker count in AIO or role 'worker' where multiple workers per container")
    parser.add_argument("--id", dest="worker_id", type=int, help="unique id for this worker")
    parser.add_argument("--role", dest="role", help="worker role", default="worker",
        choices=["manager", "watcher", "worker"])
    parser.add_argument("--restart", dest="restart", type=bool, default=None,
            help="auto restart on failure")
    parser.add_argument("--stdout", dest="stdout", action="store_true", help="send logs to stdout")
    args = parser.parse_args()

    # initialize app with initializes rest model required by all objects
    app = create_app("config.py")

    stdout = args.stdout
    if args.aio:
        fname = "allInOne.log"
    elif args.role == "manager":
        fname="%s_m%s.log" % (args.role, args.worker_id)
    elif args.role == "watcher":
        fname="%s_x%s.log" % (args.role, args.worker_id)
    else:
        fname="%s_w%s.log" % (args.role, args.worker_id)
    debug_modules = [
        "app.models.aci"
    ]
    setup_logger(logger, fname=fname, stdout=stdout)
    for l in debug_modules:
        setup_logger(logging.getLogger(l), fname=fname, stdout=stdout, thread=True)

    # validate arguments
    role = None
    restart = False if args.restart is None else args.restart
    if args.aio:
        role = "aio"
        if args.restart is None:
            restart = True
    else:
        role = args.role
        if args.worker_id is None:
            print "worker id is required for provided role"
            sys.exit(1)

    execute(
        role = role,
        count = args.count,
        worker_id = args.worker_id,
        restart = restart, 
        unique_log = (not stdout),
        debug_modules = debug_modules,
    )

