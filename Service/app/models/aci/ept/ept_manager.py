
from ... utils import get_db
from ... utils import get_redis
from .. fabric import Fabric
from .. utils import terminate_process
from . common import HELLO_INTERVAL
from . common import HELLO_TIMEOUT
from . common import MANAGER_CTRL_CHANNEL
from . common import MANAGER_WORK_QUEUE
from . common import SEQUENCE_TIMEOUT
from . common import WORKER_CTRL_CHANNEL
from . common import WORKER_UPDATE_INTERVAL
from . common import wait_for_db
from . common import wait_for_redis
from . ept_msg import MSG_TYPE
from . ept_msg import eptMsg
from . ept_msg import eptMsgHello
from . ept_queue_stats import eptQueueStats
from . ept_subscriber import eptSubscriber
from multiprocessing import Process

import logging
import threading
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class eptManager(object):
    
    # list of required roles that need to register before manager is ready to accept work
    #REQUIRED_ROLES = ["worker", "watcher", "priority"]
    REQUIRED_ROLES = ["worker", "watcher"]

    def __init__(self, worker_id):
        self.worker_id = "%s" % worker_id
        self.db = get_db()
        self.redis = get_redis()
        self.fabrics = {}               # running fabrics indexed by fabric name
        self.subscribe_thread = None
        self.stats_thread = None
        self.worker_tracker = None

        self.queue_stats_lock = threading.Lock()
        self.queue_stats = {
            WORKER_CTRL_CHANNEL: eptQueueStats.load(proc=self.worker_id, queue=WORKER_CTRL_CHANNEL),
            MANAGER_CTRL_CHANNEL: eptQueueStats.load(proc=self.worker_id, queue=MANAGER_CTRL_CHANNEL),
            MANAGER_WORK_QUEUE: eptQueueStats.load(proc=self.worker_id, queue=MANAGER_WORK_QUEUE),
            "total": eptQueueStats.load(proc=self.worker_id, queue="total"),
        }
        # initialize stats counters
        for k, q in self.queue_stats.items():
            q.init_queue()

    def __repr__(self):
        return self.worker_id

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        try:
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        finally:
            # clean up threads and running fabrics
            if self.stats_thread is not None:
                self.stats_thread.cancel()
            if self.worker_tracker is not None and self.worker_tracker.update_thread is not None:
                self.worker_tracker.update_thread.cancel()
            if self.subscribe_thread is not None:
                self.subscribe_thread.stop()
            for f, fab in self.fabrics.items():
                if fab["process"] is not None:
                    terminate_process(fab["process"])

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
        self.worker_tracker = WorkerTracker(manager=self)
        self.update_stats()

        channels = {
            WORKER_CTRL_CHANNEL: self.handle_channel_msg,
            MANAGER_CTRL_CHANNEL: self.handle_channel_msg,
        }
        p = self.redis.pubsub(ignore_subscribe_messages=True)
        p.subscribe(**channels)
        self.subscribe_thread = p.run_in_thread(sleep_time=0.01, daemon=True)
        logger.debug("[%s] listening for events on channels: %s", self, channels.keys())

        # wait for minimum workers to be ready
        while not self.minimum_workers_ready():
            time.sleep(HELLO_INTERVAL)

        # start all fabrics with auto_start enabled
        for f in Fabric.find(auto_start=True):
            self.start_fabric(f.fabric, reason="manager process start")

        logger.debug("manager %s ready for work", self.worker_id)
        # watch for work that needs to be dispatched to available workers
        while True:
            (q, data) = self.redis.blpop(MANAGER_WORK_QUEUE)
            try:
                msg = eptMsg.parse(data) 
                # expected only eptWork received on this queue
                if q == MANAGER_WORK_QUEUE and msg.msg_type == MSG_TYPE.WORK:
                    self.increment_stats(MANAGER_WORK_QUEUE, tx=False)
                    if msg.addr == 0:
                        # and addr of 0 is a broadcast to all workers of specified role
                        self.worker_tracker.broadcast(msg, qnum=msg.qnum, role=msg.role)
                    else:
                        # create hash based on address and send to specific worker
                        _hash = sum(ord(i) for i in msg.addr)
                        if not self.worker_tracker.send_msg(_hash, msg):
                            logger.warn("[%s] failed to enqueue message(%s): %s", h, msg)
                else:
                    logger.warn("[%s] unexpected messaged received on queue %s: %s", self, q, msg)

            except Exception as e:
                logger.debug("failure occurred on msg from q: %s, data: %s", q, data)
                logger.error("Traceback:\n%s", traceback.format_exc())

    def handle_channel_msg(self, msg):
        """ handle msg received on subscribed channels """
        try:
            if msg["type"] == "message":
                channel = msg["channel"]
                msg = eptMsg.parse(msg["data"]) 
                #logger.debug("[%s] msg on q(%s): %s", self, channel, msg)
                if channel == WORKER_CTRL_CHANNEL:
                    self.increment_stats(WORKER_CTRL_CHANNEL, tx=False)
                    self.worker_tracker.handle_hello(msg)
                elif channel == MANAGER_CTRL_CHANNEL:
                    self.increment_stats(MANAGER_CTRL_CHANNEL, tx=False)
                    self.handle_manager_ctrl(msg)
                else:
                    logger.warn("[%s] unsupported channel: %s", self, channel)
        except Exception as e:
            logger.debug("[%s] failed to handle msg: %s", self, msg)
            logger.error("Traceback:\n%s", traceback.format_exc())

    def handle_manager_ctrl(self, msg):
        logger.debug("ctrl message: %s, %s", msg.msg_type.value, msg.data)
        if msg.msg_type == MSG_TYPE.GET_MANAGER_STATUS:
            # return worker status along with current seq per queue and queue length
            data = {
                "manager": {
                    "manager_id": self.worker_id,
                    "queues": [MANAGER_WORK_QUEUE],
                    "queue_len": [self.redis.llen(MANAGER_WORK_QUEUE)],
                },
                "workers": self.worker_tracker.get_worker_status(),
                "fabrics": [{
                        "fabric":f, 
                        "alive": fab["process"] is not None and fab["process"].is_alive(),
                    } for f, fab in self.fabrics.items()
                ]
            }
            ret = eptMsg(MSG_TYPE.MANAGER_STATUS, data=data, seq=msg.seq)
            self.redis.publish(MANAGER_CTRL_CHANNEL, ret.jsonify())
            self.increment_stats(MANAGER_CTRL_CHANNEL, tx=True)

        elif msg.msg_type == MSG_TYPE.FABRIC_START:
            # start monitoring for fabric
            self.start_fabric(msg.data["fabric"], reason=msg.data.get("reason", None))
                
        elif msg.msg_type == MSG_TYPE.FABRIC_STOP:
            # stop a running fabric
            self.stop_fabric(msg.data["fabric"], reason=msg.data.get("reason", None))

        elif msg.msg_type == MSG_TYPE.FABRIC_RESTART:
            # restart a running (or stopped) fabric
            self.stop_fabric(msg.data["fabric"], reason=msg.data.get("reason", None))
            self.start_fabric(msg.data["fabric"], reason=msg.data.get("reason", None))

    def minimum_workers_ready(self):
        # return true if worker is ready for each required role.
        for role in eptManager.REQUIRED_ROLES:
            if role not in self.worker_tracker.active_workers or \
                len(self.worker_tracker.active_workers[role]) == 0:
                logger.debug("no active workers for role '%s'", role)
                return False
        return True

    def start_fabric(self, fabric, reason=None):
        # manager start monitoring provided fabric name.  
        # if auto_start is set disabled, then references to this fabric will be removed from manager. 
        # Else, if a new worker comes online the fabric may automatically restart.
        # return boolean success
        if reason is None: reason = "generic start"
        logger.debug("manager start fabric: %s (%s)", fabric, reason)
        if fabric not in self.fabrics:
            self.fabrics[fabric] = {
                "process": None,
                "subscriber": None,
                "waiting_for_retry": False,
                "fabric": None,
            }
        if self.fabrics[fabric]["process"] is None or not self.fabrics[fabric]["process"].is_alive():
            f = Fabric.load(fabric=fabric)
            if f.exists():
                f.add_fabric_event("starting", reason)
                # check that minimim workers are present
                if not self.minimum_workers_ready():
                    if not f.auto_start:
                        self.fabrics.pop(fabric, None)
                        f.add_fabric_event("stopped", "worker processes are not ready")
                    else: 
                        self.fabrics[fabric]["waiting_for_retry"] = True
                        f.add_fabric_event("waiting to start", "worker processes are not ready")
                    return False

                sub = eptSubscriber(f)
                self.fabrics[fabric]["subscriber"] = sub
                self.fabrics[fabric]["process"] = Process(target=sub.run)
                self.fabrics[fabric]["process"].start()
                self.fabrics[fabric]["waiting_for_retry"] = False
                return True
            else:
                logger.warn("start requested for fabric '%s' which does not exist", fabric)
                self.fabrics.pop(fabric, None)
                return False
        else:
            logger.warn("fabric '%s' already running", fabric)
            return False

    def stop_fabric(self, fabric, reason=None):
        # manager stop monitoring provided fabric name.  
        # if auto_start is disabled, then references to this fabric will be removed from manager. 
        # Else, if a new worker comes online the fabric may automatically restart.
        # return boolean success
        if reason is None: reason = "generic stop"
        logger.debug("manager stop fabric: %s (%s)", fabric, reason)
        f = Fabric.load(fabric=fabric)
        if f.exists():
            f.add_fabric_event("stopped", reason)
        if fabric not in self.fabrics:
            logger.warn("stop requested for unknown fabric '%s'", fabric)
            return False
        elif self.fabrics[fabric]["process"] is not None:
            logger.debug("terminating fabric process '%s", fabric)
            terminate_process(self.fabrics[fabric]["process"])
            self.fabrics[fabric]["process"] = None
            # need to force all workers to flush their caches for this fabric
            flush = eptMsg(MSG_TYPE.FLUSH_FABRIC, data={"fabric": fabric})
            self.worker_tracker.broadcast(flush)
            # manager should flush all events from worker queues for the fabric instead of 
            # having worker perform the operation which could lead to race conditions
            self.worker_tracker.flush_fabric(fabric)
            if not f.exists() or not f.auto_start: 
                self.fabrics.pop(fabric, None)
            else:
                self.fabrics[fabric]["waiting_for_retry"] = True
            return True

    def check_fabric_processes(self):
        # check if each running fabric is still running. If not attempt to restart process
        # triggered by worker_tracker thread at WORKER_UDPATE_INTERVAL interval
        remove_list = []
        for f, fab in self.fabrics.items():
            if fab["process"] is not None and not fab["process"].is_alive():
                # validate auto_start is enabled on the no-longer running fabric
                logger.warn("fabric %s no longer running", f)
                if Fabric.load(fabric=f).auto_start:
                    self.start_fabric(f, reason="auto restarting failed monitor")
                else: 
                    remove_list.append(f)
        # stop tracking fabrics in remove list
        for f in remove_list: self.fabrics.pop(f)

    def increment_stats(self, queue, tx=False):
        # update stats queue
        with self.queue_stats_lock:
            if queue in self.queue_stats:
                if tx:
                    self.queue_stats[queue].total_tx_msg+= 1
                    self.queue_stats["total"].total_tx_msg+= 1
                else:
                    self.queue_stats[queue].total_rx_msg+= 1
                    self.queue_stats["total"].total_rx_msg+= 1

    def update_stats(self):
        # update stats at regular interval for all queues
        with self.queue_stats_lock:
            for k, q in self.queue_stats.items():
                q.collect(qlen = self.redis.llen(k))

        # set timer to recollect at next collection interval
        self.stats_thread = threading.Timer(eptQueueStats.STATS_INTERVAL, self.update_stats)
        self.stats_thread.daemon = True
        self.stats_thread.start()

        
class WorkerTracker(object):
    # track list of active workers 
    def __init__(self, manager=None):
        self.manager = manager
        self.redis = self.manager.redis
        self.known_workers = {}     # indexed by worker_id
        self.active_workers = {}    # list of active workers indexed by role
        self.update_interval = WORKER_UPDATE_INTERVAL # interval to check for new/expired workers
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
                self.known_workers[hello.worker_id].queue_locks.append(threading.Lock())
                if q not in self.manager.queue_stats:
                    self.manager.queue_stats[q] = eptQueueStats(proc=self.manager.worker_id,queue=q)
                    self.manager.queue_stats[q].init_queue()
            # wait until background thread picks up update and adds to available workers
            logger.debug("new worker(%s) detected, waiting for activation period",hello.worker_id)
        else:
            self.known_workers[hello.worker_id].last_hello = time.time()

    def update_active_workers(self):
        # at a regular interval, check for new workers to add to active worker queue along with
        # removal of inactive workers.  This runs in a background thread independent of hello.  
        # Therefore, the time to detect a new worker is potential 2x update timer
        # This also triggers fabric check on manager to ensure all subscriber processes are still
        # running.
        ts = time.time()
        remove_workers = []
        new_workers = False
        for wid, w in self.known_workers.items():
            if w.last_hello + HELLO_TIMEOUT < ts:
                logger.warn("worker timeout (last hello: %.3f) %s",ts-w.last_hello, w)
                remove_workers.append(w)
            elif not w.active:
                # new worker that needs to be added to active list
                logger.info("new worker: %s", w)
                if w.role not in self.active_workers: self.active_workers[w.role] = []
                self.active_workers[w.role].append(w)
                w.active = True
                new_workers = True
                # trigger fabric restarts if any are in 'waiting_for_retry' state
                for f, fab in self.manager.fabrics.items():
                    if fab["waiting_for_retry"]:
                        self.manager.start_fabric(f, reason="new worker '%s' online" % wid)
            #elif w.last_head_check + SEQUENCE_TIMEOUT < ts:
            #    # check if seq is stuck on any queue which indicates a problem with the worker
            #    for i, last_head in enumerate(w.last_head):
            #        head = self.redis.lindex(w.queues[i], 0)
            #        if head is None:
            #            w.last_head[i] = 0
            #        elif last_head > 0 and last_head == head:
            #            logger.warn("worker seq stuck on q:%s, seq:%s %s", w.queues[i], head, w)
            #            remove_workers.append(w)
            #            break
            #        else:
            #            w.last_head[i] = head
            #    self.last_head_check = ts

        # remove workers from known_workers and active_workers
        for w in remove_workers:
            logger.debug("removing worker from known_workers: %s", w)
            self.known_workers.pop(w.worker_id, None)
            if w.role in self.active_workers and w in self.active_workers[w.role]:
                logger.debug("removing worker from active_workers[%s]: %s", w.role, w)
                self.active_workers[w.role].remove(w)
            # if a worker has died, when need to trigger a monitor restart for all fabrics and 
            # flush out current worker queues to prevent stale work in redis incase worker comes
            # back online
            for i, q in enumerate(w.queues):
                logger.debug("deleting work from queue: %s", q)
                with w.queue_locks[i]:
                    self.redis.delete(q)
            # restart all fabrics
            for f in self.manager.fabrics.keys():
                self.manager.stop_fabric(f, reason="worker '%s' no longer active" % w.worker_id)
                self.manager.start_fabric(f, reason="restarting after active worker change")

        if len(remove_workers)>0 or new_workers:
            logger.info("total workers: %s", len(self.known_workers))

        # trigger manager fabric processes check
        self.manager.check_fabric_processes()

        # schedule next worker check
        self.update_thread = threading.Timer(self.update_interval, self.update_active_workers)
        self.update_thread.daemon = True
        self.update_thread.start()

    def send_msg(self, _hash, msg):
        # get number of active workers for msg.role and using modulo on _hash to select a worker
        # add the work to corresponding worker queue and increment seq number.  
        # msg must be type eptMsgWorker 
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
        with worker.queue_locks[msg.qnum]:
            worker.last_seq[msg.qnum]+= 1
            msg.seq = worker.last_seq[msg.qnum]
            logger.debug("enqueue %s: %s", worker.queues[msg.qnum], msg)
            self.redis.rpush(worker.queues[msg.qnum], msg.jsonify())
            self.manager.increment_stats(worker.queues[msg.qnum], tx=True)
        return True

    def broadcast(self, msg, qnum=0, role=None):
        # broadcast message to active workers on particular queue index.  Set role to limit the 
        # broadcast to only workers of particular role
        logger.debug("broadcast [q:%s, r:%s] msg: %s", qnum, role, msg)
        for r in self.active_workers:
            if role is None or r == role:
                for i, worker in enumerate(self.active_workers[r]):
                    if qnum > len(worker.queues):
                        logger.warn("unable to broadcast msg on worker %s, qnum %s does not exist",
                            worker.worker_id, qnum)
                    else:
                        with worker.queue_locks[qnum]:
                            worker.last_seq[qnum]+= 1
                            msg.seq = worker.last_seq[qnum]
                            self.redis.rpush(worker.queues[qnum], msg.jsonify())
                            self.manager.increment_stats(worker.queues[qnum], tx=True)

    def flush_fabric(self, fabric, qnum=-1, role=None):
        # walk through all active workers and remove any work objects from queue for this fabric
        # note, this is a costly operation if the queue is significantly backed up...
        logger.debug("flush fabric '%s'", fabric)
        for r in self.active_workers:
            if role is None or r == role:
                for i, worker in enumerate(self.active_workers[r]):
                    if abs(qnum) > len(worker.queues):
                        logger.warn("unable to flush fabric for worker %s, qnum %s does not exist",
                                worker.worker_id, qnum)
                    else:
                        # pull off all messages on the queue in single operation
                        pl = self.redis.pipeline()
                        pl.lrange(worker.queues[qnum], 0, -1)
                        pl.delete(worker.queues[qnum])
                        ret = []
                        repush = []
                        removed_count = 0
                        with worker.queue_locks[qnum]:
                            ret = pl.execute()
                        # inspect each message and if matching fabric discard, else push back onto
                        # worker's queue
                        if len(ret) > 0 and type(ret[0]) is list:
                            logger.debug("inspecting %s msg from queue %s", len(ret[0]), 
                                                                            worker.queues[qnum])
                            for data in ret[0]:
                                # need to reparse message and check fabric
                                msg = eptMsg.parse(data) 
                                if hasattr(msg, "fabric") and msg.fabric == fabric:
                                    removed_count+=1
                                else:
                                    repush.append(data)
                        logger.debug("queue %s, removed %s msg for fabric %s, repushing %s",
                                        worker.queues[qnum], removed_count, fabric, len(repush))
                        if len(repush) > 0:
                            with worker.queue_locks[qnum]:
                                self.redis.rpush(worker.queues[qnum], *repush)

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
        self.queue_locks = []           # list of thread locks per queue
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

