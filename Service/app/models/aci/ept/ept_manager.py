
from ... utils import get_app_config
from ... utils import get_db
from . common import HELLO_INTERVAL
from . common import HELLO_TIMEOUT
from . common import MANAGER_CTRL_CHANNEL
from . common import MANAGER_WORK_QUEUE
from . common import SEQUENCE_TIMEOUT
from . common import WORKER_CTRL_CHANNEL
from . common import wait_for_db
from . common import wait_for_redis
from . ept_msg import eptMsg
from . ept_msg import eptMsgHello

import logging
import redis
import threading
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class eptManager(object):
    
    def __init__(self, worker_id):
        self.worker_id = "%s" % worker_id
        self.app_config = get_app_config()
        self.db = get_db()
        self.redis = redis.StrictRedis(host=self.app_config["REDIS_HOST"], 
                            port=self.app_config["REDIS_PORT"], db=self.app_config["REDIS_DB"])
        self.subscribe_thread = None
        self.stats_thread = None
        self.worker_tracker = None
        self.stats_interval = 60.0
        self.stats_last_time = 0
        self.stats_last_total_tx_msg = 0
        self.stats_last_total_rx_msg = 0
        self.stats_tx_msg_rate = 0.0
        self.stats_rx_msg_rate = 0.0
        self.stats_total_rx_msg = 0
        self.stats_total_tx_msg = 0

    def __repr__(self):
        return self.worker_id

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        try:
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        finally:
            if self.stats_thread is not None:
                self.stats_thread.cancel()
            if self.worker_tracker is not None and self.worker_tracker.update_thread is not None:
                self.worker_tracker.update_thread.cancel()
            if self.subscribe_thread is not None:
                self.subscribe_thread.stop()

    def _run(self):
        """ start manager 
            manager listens on the following queues:
                - WORKER_CTRL_CHANNEL for worker registration/keepalives
                - MANAGER_CTRL_CHANNEL for request for manager start/stop/status
                - MANAGER_WORK_QUEUE for work that needs to be dispatched to a worker node
        """
        # first check/wait on redis and mongo connection, then start
        wait_for_redis(self.redis)
        wait_for_db(self.db)
        self.worker_tracker = WorkerTracker(self.redis)
        self.update_stats()

        channels = {
            WORKER_CTRL_CHANNEL: self.handle_channel_msg,
            MANAGER_CTRL_CHANNEL: self.handle_channel_msg,
        }
        p = self.redis.pubsub(ignore_subscribe_messages=True)
        p.subscribe(**channels)
        #self.subscribe_thread = p.run_in_thread(sleep_time=0.001)
        self.subscribe_thread = p.run_in_thread()
        logger.debug("[%s] listening for events on channels: %s", self, channels.keys())

        # wait until there are some workers active
        while True:
            if len(self.worker_tracker.active_workers) == 0:
                logger.debug("waiting for active workers")
                time.sleep(HELLO_INTERVAL)
            else: break

        logger.debug("listening for work!")
        # watch for work that needs to be dispatched to available workers
        while True:
            (q, data) = self.redis.blpop(MANAGER_WORK_QUEUE)
            try:
                self.stats_total_rx_msg+= 1
                msg = eptMsg.parse(data) 
                # expected only eptWork received on this queue
                if q == MANAGER_WORK_QUEUE and msg.msg_type == "work":
                    # create hash based on address
                    _hash = sum(ord(i) for i in msg.addr)
                    if not self.worker_tracker.send_msg(_hash, msg):
                        logger.warn("[%s] failed to enqueue message(%s): %s", h, msg)
                    else:
                        self.stats_total_tx_msg+= 1
                else:
                    logger.warn("[%s] unexpected messaged received on queue %s: %s", self, q, msg)

            except Exception as e:
                logger.debug("failure occurred on msg from q: %s, data: %s", q, data)
                logger.error("Traceback:\n%s", traceback.format_exc())


    def handle_channel_msg(self, msg):
        """ handle msg received on subscribed channels """
        try:
            self.stats_total_rx_msg+= 1
            if msg["type"] == "message":
                channel = msg["channel"]
                msg = eptMsg.parse(msg["data"]) 
                #logger.debug("[%s] msg on q(%s): %s", self, channel, msg)
                if channel == WORKER_CTRL_CHANNEL:
                    self.worker_tracker.handle_hello(msg)
                elif channel == MANAGER_CTRL_CHANNEL:
                    self.handle_manager_ctrl(msg)
                else:
                    logger.warn("[%s] unsupported channel: %s", self, channel)
        except Exception as e:
            logger.debug("[%s] failed to handle msg: %s", self, msg)
            logger.error("Traceback:\n%s", traceback.format_exc())

    def handle_manager_ctrl(self, msg):
        logger.debug("ctrl message: %s, %s", msg.msg_type, msg.data)
        if msg.msg_type == "get_status":
            # return worker status along with current seq per queue and queue length
            data = {
                "manager": {
                    "id": self.worker_id,
                    "total_tx_msg": self.stats_total_tx_msg,
                    "total_rx_msg": self.stats_total_rx_msg,
                    "tx_msg_rate": self.stats_tx_msg_rate,
                    "rx_msg_rate": self.stats_rx_msg_rate,
                    "stats_interval": self.stats_interval,
                    "queues": [MANAGER_WORK_QUEUE],
                    "queue_len": [self.redis.llen(MANAGER_WORK_QUEUE)],
                },
                "workers": self.worker_tracker.get_worker_status(),
                "fabrics": []
            }
            ret = eptMsg("status", data=data, seq=msg.seq)
            self.redis.publish(MANAGER_CTRL_CHANNEL, ret.jsonify())
            self.stats_total_tx_msg+=1
        elif msg.msg_type == "start_fabric":
            pass
        elif msg.msg_type == "stop_fabric":
            pass

    def update_stats(self):
        # update stats at regular interval - will save to db with wrap later
        # for now just tracking msg_rate 
        ts = time.time()
        if self.stats_last_time == 0:
            self.stats_last_time = ts
        else:
            d = ts - self.stats_last_time
            tx = self.stats_total_tx_msg - self.stats_last_total_tx_msg
            rx = self.stats_total_rx_msg - self.stats_last_total_rx_msg
            if d > 0:
                self.stats_tx_msg_rate = tx / d
                self.stats_rx_msg_rate = rx / d
            self.stats_last_total_tx_msg = self.stats_total_tx_msg
            self.stats_last_total_rx_msg = self.stats_total_rx_msg

        self.stats_thread = threading.Timer(self.stats_interval, self.update_stats)
        self.stats_thread.daemon = True
        self.stats_thread.start()
        
        
class WorkerTracker(object):
    # track list of active workers 
    def __init__(self, redis_db):
        self.redis = redis_db
        self.known_workers = {}     # indexed by worker_id
        self.active_workers = {}    # list of active workers indexed by role
        self.update_interval = 10.0 # interval to check for new/expired workers
        self.update_thread = None
        self.update_active_workers()

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
            self.known_workers[hello.worker_id].hello_seq = hello.seq
            for q in hello.queues:
                self.known_workers[hello.worker_id].last_seq.append(0)
                self.known_workers[hello.worker_id].last_head.append(0)
            # wait until background thread picks up update and adds to available workers
            logger.debug("new worker(%s) detected, waiting for activation period",hello.worker_id)
        else:
            self.known_workers[hello.worker_id].last_hello = time.time()

    def update_active_workers(self):
        # at a regular interval, check for new workers to add to active worker queue along with
        # removal of inactive workers.  This runs in a background thread independent of hello.  
        # Therefore, the time to detect a new worker is potential 2x update timer
        ts = time.time()
        remove_workers = []
        new_workers = False
        for wid, w in self.known_workers.items():
            if w.last_hello + HELLO_TIMEOUT < ts:
                logger.warn("worker timeout (%0.3f < %0.3f) %s",w.last_hello+HELLO_TIMEOUT,ts,w)
                remove_workers.append(w)
            elif not w.active:
                # new worker that needs to be added to active list
                logger.info("new worker: %s", w)
                if w.role not in self.active_workers: self.active_workers[w.role] = []
                self.active_workers[w.role].append(w)
                w.active = True
                new_workers = True
            elif w.last_head_check + SEQUENCE_TIMEOUT < ts:
                # check if seq is stuck on any queue which indicates a problem with the worker
                for i, last_head in enumerate(w.last_head):
                    head = self.redis.lindex(w.queues[i], 0)
                    if head is None:
                        w.last_head[i] = 0
                    elif last_head > 0 and last_head == head:
                        logger.warn("worker seq stuck on q:%s, seq:%s %s", w.queues[i], head, w)
                        remove_workers.append(w)
                        break
                    else:
                        w.last_head[i] = head
                self.last_head_check = ts

        # remove workers from known_workers and active_workers
        for w in remove_workers:
            logger.debug("removing worker from known_workers: %s", w)
            self.known_workers.pop(w.worker_id, None)
            if w.role in self.active_workers and w in self.active_workers[w.role]:
                logger.debug("removing worker from active_workers[%s]: %s", w.role, w)
                self.active_workers[w.role].remove(w)
        if len(remove_workers)>0 or new_workers:
            logger.info("total workers: %s", len(self.known_workers))

        # schedule next worker check
        self.update_thread = threading.Timer(self.update_interval, self.update_active_workers)
        self.update_thread.daemon = True
        self.update_thread.start()

    def send_msg(self, _hash, msg):
        # get number of active workers for msg.role and using modulo on _hash to select a worker
        # add the work to corresponding worker queue and increment seq number.  
        # return boolean success
        if msg.role not in self.active_workers or len(self.active_workers[msg.role]) == 0:
            logger.warn("no available workers for role '%s'", msg.role)
            return False
        index = _hash % len(self.active_workers[msg.role])
        worker = self.active_workers[msg.role][index]
        if msg.qnum >= len(worker.queues):
            logger.warn("unable to enqueue work on worker %s, queue %s does not exist", 
                worker.worker_id, msg.qnum)
            return False
        worker.last_seq[msg.qnum]+= 1
        msg.seq = worker.last_seq[msg.qnum]
        #logger.debug("enqueuing work onto queue %s: %s", worker.queues[msg.qnum], msg)
        self.redis.rpush(worker.queues[msg.qnum], msg.jsonify())
        return True

    def get_worker_status(self):
        # return list of dict representation of TrackedWorker objects along with queue_len list 
        # which is number of jobs currently in each queue
        status = []
        for wid, w in self.known_workers.items():
            js = w.to_json()
            js["queue_len"] = [self.redis.llen(q) for q in w.queues]
            status.append(js)
        return status
            

class TrackedWorker(object):
    """ active worker tracker """
    def __init__(self, worker_id):
        self.worker_id = worker_id
        self.active = False             # set to true when added to active list
        self.queues = []                # queue names sorted by priority
        self.role = None
        self.start_time = 0
        self.hello_seq = 0
        self.last_hello = 0
        self.last_seq = []              # last seq enqueued on worker per queue
        self.last_head = []             # at time of last worker check, seq at head of queue
        self.last_head_check = 0        # timestamp of last head seq check

    def __repr__(self):
        return "%s, role:%s, q:%s" % (self.worker_id,self.role,self.queues)

    def to_json(self):
        return {
            "worker_id": self.worker_id,
            "active": self.active,
            "queues": self.queues,
            "role": self.role,
            "start_time": self.start_time,
            "hello_seq": self.hello_seq,
            "last_hello": self.last_hello,
            "last_seq": self.last_seq
        }

