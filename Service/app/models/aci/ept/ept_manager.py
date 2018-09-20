
from ... utils import get_app_config
from ... utils import get_db
from . common import HELLO_CHANNEL
from . common import HELLO_TIMEOUT
from . common import MANAGER_CTRL_CHANNEL
from . common import wait_for_db
from . common import wait_for_redis
from . ept_msg import EPTMsg
from . ept_msg import EPTMsgHello

import logging
import redis
import threading
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class EPTManager(object):
    
    def __init__(self, worker_id):
        self.worker_id = "%s" % worker_id
        self.app_config = get_app_config()
        self.db = get_db()
        self.redis = redis.StrictRedis(host=self.app_config["REDIS_HOST"], 
                            port=self.app_config["REDIS_PORT"], db=self.app_config["REDIS_DB"])
        self.subscribe_thread = None
        self.worker_tracker = None

    def __repr__(self):
        return self.worker_id

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        try:
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
            if self.worker_tracker is not None:
                self.worker_tracker.update_thread_kill = True
            if self.subscribe_thread is not None:
                self.subscribe_thread.stop()

    def _run(self):
        """ start manager 
            manager listens on the following queues:
                - HELLO_CHANNEL for worker registration/keepalives
                - MANAGER_CTRL_CHANNEL for request for manager start/stop/status
        """
        # first check/wait on redis and mongo connection, then start
        wait_for_redis(self.redis)
        wait_for_db(self.db)
        self.worker_tracker = WorkerTracker(self.redis)

        channels = {
            HELLO_CHANNEL: self.handle_channel_msg,
            MANAGER_CTRL_CHANNEL: self.handle_channel_msg,
        }
        p = self.redis.pubsub(ignore_subscribe_messages=True)
        p.subscribe(**channels)
        self.subscribe_thread = p.run_in_thread(sleep_time=0.001)
        logger.debug("[%s] listening for events on channels: %s", self, channels.keys())
        # sleep forever
        while True: time.sleep(3600)
        logger.error("[%s] manager pubsub thread unexpectedly ended", self)

    def handle_channel_msg(self, msg):
        """ handle msg received on subscribed channels """
        try:
            if msg["type"] == "message":
                channel = msg["channel"]
                msg = EPTMsg.parse(msg["data"]) 
                #logger.debug("[%s] msg on q(%s): %s", self, channel, msg)
                if channel == HELLO_CHANNEL:
                    self.worker_tracker.handle_hello(msg)
                elif channel == MANAGER_CTRL_CHANNEL:
                    self.handle_manager_ctrl(msg)
                else:
                    logger.warn("[%s] unsupported channel: %s", self, channel)
        except Exception as e:
            logger.debug("[%s] failed to handle msg: %s", self, msg)
            logger.error("Traceback:\n%s", traceback.format_exc())

    def handle_manager_ctrl(self, msg):
        logger.debug("ctrl message: %s", msg)


class WorkerTracker(object):
    # track list of active workers 
    def __init__(self, redis_db):
        self.redis = redis_db
        self.update_timer = 10.0    # interval to check for new/expired workers
        self.known_workers = {}     # indexed by worker_id
        self.active_workers = {}    # list of active workers indexed by role
        self.update_thread_kill = False
        self.update_thread = threading.Thread(target=self.update_available_workers)
        self.update_thread.start()

    def handle_hello(self, hello):
        # handle worker hello, add to known workers if unknown
        if hello.worker_id not in self.known_workers:
            if len(hello.queues) == 0:
                logger.warn("invalid worker, no available work queues: %s", hello)
                return
            self.known_workers[hello.worker_id] = TrackedWorker(hello.worker_id)
            self.known_workers[hello.worker_id].role = hello.role
            self.known_workers[hello.worker_id].start_time = hello.start_time
            self.known_workers[hello.worker_id].queues = hello.queues
            self.known_workers[hello.worker_id].last_hello = time.time()
            for q in hello.queues:
                self.known_workers[hello.worker_id].last_seq.append(0)
            # wait until background thread picks up update and adds to available workers
        else:
            self.known_workers[hello.worker_id].last_hello = time.time()

    def update_available_workers(self):
        # at a regular interval, check for new workers to add to active worker queue along with
        # removal of inactive workers.  This runs in a background thread independent of hello.  
        # Therefore, the time to detect a new worker is potential 2x update timer
        while not self.update_thread_kill:
            ts = time.time()
            remove_workers = []
            new_workers = False
            for wid, w in self.known_workers.items():
                if w.last_hello + HELLO_TIMEOUT < ts:
                    logger.warn("worker timeout (%0.3f < %0.3f) %s",w.last_hello+HELLO_TIMEOUT,ts,w)
                    remove_workers.append(w)
                elif not w.active:
                    # newly worker that needs to be added to active list
                    logger.info("new worker: %s", w)
                    if w.role not in self.active_workers: self.active_workers[w.role] = []
                    self.active_workers[w.role].append(w)
                    w.active = True
                    new_workers = True
                else:
                    # check if seq is stuck on any queue which indicates a problem with the worker
                    for i, seq in enumerate(w.last_seq):
                        head = self.redis.lindex(w.queues[i], 0)
                        if head is None:
                            w.last_seq[i] = 0
                        else:
                            if seq == 0: w.last_seq[i] = head
                            elif head == seq:
                                logger.warn("worker seq stuck on q:%s, seq:%s %s",w.queues[i],seq,w)
                                remove_workers.append(w)
                                break

            # remove workers from known_workers and active_workers
            for w in remove_workers:
                logger.debug("removing worker from known_workers: %s", w)
                self.known_workers.pop(w.worker_id, None)
                if w.role in self.active_workers and w in self.active_workers[w.role]:
                    logger.debug("removing worker from active_workers[%s]: %s", w.role, w)
                    self.active_workers[w.role].remove(w)
            if len(remove_workers)>0 or new_workers:
                logger.info("total workers: %s", len(self.known_workers))

            time.sleep(self.update_timer)
            

class TrackedWorker(object):
    """ active worker tracker """
    def __init__(self, worker_id):
        self.worker_id = worker_id
        self.active = False             # set to true when added to active list
        self.queues = []                # queue names sorted by priority
        self.role = None
        self.start_time = 0
        self.last_hello = 0
        self.last_seq = []              # last seq enqueued on worker per queue

    def __repr__(self):
        return "%s, role:%s, q:%s" % (self.worker_id,self.role,self.queues)

