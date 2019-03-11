
from ... utils import get_db
from ... utils import get_redis
from .. fabric import Fabric
from .. utils import raise_interrupt
from .. utils import register_signal_handlers
from .. utils import terminate_process
from . common import HELLO_INTERVAL
from . common import HELLO_TIMEOUT
from . common import MANAGER_CTRL_CHANNEL
from . common import MANAGER_CTRL_RESPONSE_CHANNEL
from . common import MANAGER_WORK_QUEUE
from . common import SEQUENCE_TIMEOUT
from . common import SUPPRESS_FABRIC_RESTART
from . common import WORKER_CTRL_CHANNEL
from . common import WORKER_UPDATE_INTERVAL
from . common import BackgroundThread
from . common import db_alive
from . common import get_queue_length
from . common import wait_for_db
from . common import wait_for_redis
from . ept_msg import MSG_TYPE
from . ept_msg import WORK_TYPE
from . ept_msg import eptMsg
from . ept_msg import eptMsgBulk
from . ept_msg import eptMsgHello
from . ept_queue_stats import eptQueueStats
from . ept_subscriber import eptSubscriber
from multiprocessing import Process

import logging
import re
import signal
import time
import threading
import traceback

# module level logging
logger = logging.getLogger(__name__)

class eptManager(object):
    
    # list of required roles that need to register before manager is ready to accept work
    #REQUIRED_ROLES = ["worker", "watcher", "priority"]
    REQUIRED_ROLES = ["worker", "watcher"]

    def __init__(self, worker_id):
        logger.debug("init role manager id %s", worker_id)
        register_signal_handlers()
        self.worker_id = "%s" % worker_id
        self.db = get_db(uniq=True, overwrite_global=True, write_concern=True)
        self.redis = get_redis()
        self.fabrics = {}               # running fabrics indexed by fabric name
        self.subscribe_thread = None
        self.stats_thread = None
        self.worker_tracker = None

        self.queue_stats_lock = threading.Lock()
        self.queue_stats = {
            WORKER_CTRL_CHANNEL: eptQueueStats.load(proc=self.worker_id, queue=WORKER_CTRL_CHANNEL),
            MANAGER_CTRL_CHANNEL: eptQueueStats.load(proc=self.worker_id, queue=MANAGER_CTRL_CHANNEL),
            MANAGER_CTRL_RESPONSE_CHANNEL: eptQueueStats.load(proc=self.worker_id, 
                                                queue=MANAGER_CTRL_RESPONSE_CHANNEL),
            MANAGER_WORK_QUEUE: eptQueueStats.load(proc=self.worker_id, queue=MANAGER_WORK_QUEUE),
            "total": eptQueueStats.load(proc=self.worker_id, queue="total"),
        }
        # initialize stats counters
        for k, q in self.queue_stats.items():
            q.init_queue()

    def __repr__(self):
        return self.worker_id

    def cleanup(self):
        """ graceful cleanup on exit """
        if self.stats_thread is not None:
            self.stats_thread.exit()
        if self.worker_tracker is not None and self.worker_tracker.update_thread is not None:
            self.worker_tracker.update_thread.exit()
        if self.subscribe_thread is not None:
            self.subscribe_thread.stop()
        for f, fab in self.fabrics.items():
            if fab["process"] is not None:
                terminate_process(fab["process"])
        if self.db is not None:
            self.db.client.close()
        if self.redis is not None and self.redis.connection_pool is not None:
            self.redis.connection_pool.disconnect()

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        try:
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        finally:
            self.cleanup()

    def _run(self):
        """ start manager 
            manager listens on the following queues:
                - WORKER_CTRL_CHANNEL for worker registration/keepalives
                - MANAGER_CTRL_CHANNEL for request for manager start/stop/status
                - MANAGER_WORK_QUEUE for work that needs to be dispatched to a worker node
        """
        # first check/wait on redis and mongo connection, then start
        wait_for_redis(self.redis)
        # as soon as redis is online, manager must trigger a flush to purge any old data
        logger.info("manager only, flushing full redis db")
        self.redis.flushall()
        wait_for_db(self.db)
        self.worker_tracker = WorkerTracker(manager=self)
        self.stats_thread = BackgroundThread(func=self.update_stats, name="stats", count=0, 
                                            interval= eptQueueStats.STATS_INTERVAL)
        self.stats_thread.daemon = True
        self.stats_thread.start()

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
            self.start_fabric(f.fabric, reason="manager process start", skip_suppress=True)

        logger.debug("manager %s ready for work", self.worker_id)
        # watch for work that needs to be dispatched to available workers
        while True:
            (q, data) = self.redis.blpop(MANAGER_WORK_QUEUE)
            # to support msg type BULK, assume an array of messages received
            msg_list = []
            try:
                omsg = eptMsg.parse(data) 
                #logger.debug("[%s] msg on q(%s): %s", self, q, omsg)
                if omsg.msg_type == MSG_TYPE.BULK:
                    msg_list = omsg.msgs
                elif omsg.msg_type == MSG_TYPE.WORK:
                    msg_list = [omsg]
                else:
                    logger.warn("[%s] unexpected messaged received on queue %s: %s", self, q, msg)

                bulk = []   # list of (hash, msg) to execute against send_bulk
                for msg in msg_list:
                    # expected only eptWork received on this queue
                    if q == MANAGER_WORK_QUEUE and msg.msg_type == MSG_TYPE.WORK:
                        self.increment_stats(MANAGER_WORK_QUEUE, tx=False)
                        if msg.addr == 0:
                            # an addr of 0 is a broadcast to all workers of specified role.
                            # Send broadcast now, not within a batch.
                            # Note, broadcast may be out of order if received in BULK with ucast msg
                            self.worker_tracker.broadcast(msg, qnum=msg.qnum, role=msg.role)
                        else:
                            # create hash based on address and send to specific worker
                            # need to ensure that we hash on ip for EPM_RS_IP_EVENT so it goes to the 
                            # correct worker...
                            if msg.wt == WORK_TYPE.EPM_RS_IP_EVENT:
                                _hash = sum(ord(i) for i in msg.ip)
                            else:
                                _hash = sum(ord(i) for i in msg.addr)
                            bulk.append((_hash, msg))
                if len(bulk) > 0:
                    if not self.worker_tracker.send_bulk(bulk):
                        logger.warn("[%s] failed to enqueue one or more messages", self)

            except Exception as e:
                logger.debug("failed to parse message from q: %s, data: %s", q, data)
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
        logger.debug("ctrl message: %s, seq:0x%x, %s", msg.msg_type.value, msg.seq, msg.data)
        if msg.msg_type == MSG_TYPE.GET_MANAGER_STATUS:
            # publish manager status in background thread (to ensure we don't block other requests)
            # note if brief is set to False, then this request can take significant time to read 
            # and analyze all requests queued.
            kwargs = {"seq": msg.seq, "brief": msg.data.get("brief", True)}
            tmp = threading.Thread(target=self.publish_manager_status, name="status", kwargs=kwargs)
            tmp.daemon = True
            tmp.start()

        elif msg.msg_type == MSG_TYPE.GET_FABRIC_STATUS:
            # publish alive status for single fabric
            if "fabric" in msg.data:
                self.publish_fabric_status(msg.data["fabric"], seq=msg.seq)
            else:
                logger.warn("fabric status request without fabric present")

        elif msg.msg_type == MSG_TYPE.FABRIC_START:
            # start monitoring for fabric
            self.start_fabric(msg.data["fabric"], reason=msg.data.get("reason", None), 
                             skip_suppress=True)
                
        elif msg.msg_type == MSG_TYPE.FABRIC_STOP:
            # stop a running fabric
            self.stop_fabric(msg.data["fabric"], reason=msg.data.get("reason", None))

        elif msg.msg_type == MSG_TYPE.FABRIC_RESTART:
            # restart a running (or stopped) fabric
            self.stop_fabric(msg.data["fabric"], reason=msg.data.get("reason", None))
            self.start_fabric(msg.data["fabric"], reason=msg.data.get("reason", None),
                              skip_suppress=True)

        elif msg.msg_type == MSG_TYPE.GET_WORKER_HASH:
            # requires addr field only and returns hash, index, and selected worker
            if "addr" in msg.data:
                if "worker" in self.worker_tracker.active_workers:
                    _hash = sum(ord(i) for i in msg.data["addr"])
                    index = _hash % len(self.worker_tracker.active_workers["worker"])
                    worker = self.worker_tracker.active_workers["worker"][index]
                    data = {
                        "addr": msg.data["addr"],
                        "hash": _hash,
                        "index": index,
                        "worker": worker.worker_id,
                    }
                    ret = eptMsg(MSG_TYPE.WORKER_HASH, data=data, seq=msg.seq)
                    self.redis.publish(MANAGER_CTRL_RESPONSE_CHANNEL, ret.jsonify())
                    self.increment_stats(MANAGER_CTRL_RESPONSE_CHANNEL, tx=True)
            else:
                logger.warn("worker hash request with no address field")
        else:
            logger.debug("ignoring msg type received on manager ctrl: %s", msg.msg_type)

    def publish_manager_status(self, seq=0, brief=False):
        # get manager status in background thread and publish result on ctrl response channel
        try:
            start_ts = time.time()
            data = {
                "manager": {
                    "manager_id": self.worker_id,
                    "queues": [MANAGER_WORK_QUEUE],
                    "queue_len":[get_queue_length(self.redis,MANAGER_WORK_QUEUE,accurate=not brief)],
                },
                "workers": self.worker_tracker.get_worker_status(brief=brief),
                "fabrics": [{
                        "fabric":f, 
                        "alive": fab["process"] is not None and fab["process"].is_alive(),
                    } for f, fab in self.fabrics.items()
                ]
            }
            total_queue_len = sum(data["manager"]["queue_len"])
            for w in data["workers"]:
                if "queue_len" in w:
                    total_queue_len+= sum(w["queue_len"])
            data["total_queue_len"] = total_queue_len
            logger.debug("manager status (ts: %.3f, seq:0x%x, queue: %s, workers: %s, fabrics: %s)", 
                    time.time()-start_ts, seq, total_queue_len, 
                    len(data["workers"]),
                    len(data["fabrics"])
                )
            ret = eptMsg(MSG_TYPE.MANAGER_STATUS, data=data, seq=seq)
            self.redis.publish(MANAGER_CTRL_RESPONSE_CHANNEL, ret.jsonify())
            self.increment_stats(MANAGER_CTRL_RESPONSE_CHANNEL, tx=True)
        except Exception as e:
            logger.debug("[%s] failed to get manager status", self)
            logger.error("Traceback:\n%s", traceback.format_exc())

    def publish_fabric_status(self, fabric, seq=0):
        # publish alive status for a single fabric to ctrl response channel
        try:
            alive = False
            if fabric in self.fabrics:
                fab = self.fabrics[fabric]
                if fab["process"] is not None and fab["process"].is_alive():
                    alive = True
            data = {
                "fabric": fabric,
                "alive": alive
            }
            logger.debug("fabric %s alive:%r (seq:0x%x)", fabric, alive, seq)
            ret = eptMsg(MSG_TYPE.FABRIC_STATUS, data=data, seq=seq)
            self.redis.publish(MANAGER_CTRL_RESPONSE_CHANNEL, ret.jsonify())
            self.increment_stats(MANAGER_CTRL_RESPONSE_CHANNEL, tx=True)
        except Exception as e:
            logger.debug("[%s] failed to get manager status", self)
            logger.error("Traceback:\n%s", traceback.format_exc())

    def minimum_workers_ready(self):
        # return true if worker is ready for each required role.
        for role in eptManager.REQUIRED_ROLES:
            if role not in self.worker_tracker.active_workers or \
                len(self.worker_tracker.active_workers[role]) == 0:
                logger.debug("no active workers for role '%s'", role)
                return False
        return True

    def start_fabric(self, fabric, reason=None, restarting=False, skip_suppress=False):
        # manager start monitoring provided fabric name.  
        # if auto_start is disabled, then references to this fabric will be removed from manager 
        # on failure. Else, if a new worker comes online the fabric may automatically restart.
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
                # check start suppression threshold
                ts_delta = (time.time() - f.restart_ts)
                if ts_delta < SUPPRESS_FABRIC_RESTART and not skip_suppress:
                    logger.debug("suppressing fabric %s restart (%.3f < %.3f)", fabric, ts_delta, 
                            SUPPRESS_FABRIC_RESTART)
                    self.fabrics[fabric]["waiting_for_retry"] = True
                    return False

                # check that minimim workers are present
                if not self.minimum_workers_ready():
                    if not restarting:
                        f.add_fabric_event("starting", reason)
                        f.add_fabric_event("waiting to start", "worker processes are not ready")
                    return False

                f.add_fabric_event("starting", reason)
                sub = eptSubscriber(f, active_workers=self.worker_tracker.active_workers)
                self.fabrics[fabric]["subscriber"] = sub
                self.fabrics[fabric]["process"] = Process(target=sub.run)
                self.fabrics[fabric]["process"].daemon = True
                self.fabrics[fabric]["process"].start()
                self.fabrics[fabric]["waiting_for_retry"] = False
                # save start time to fabric object to suppress rapid restarts
                start_ts = time.time()
                f.restart_ts = start_ts
                f.save()
                # help notification to workers that new fabric is present - mostly needed for 
                # watchers but can be sent to all workers to pre-load their caches with fabric 
                # settings for this fabric.
                start = eptMsg(MSG_TYPE.FABRIC_START, data={"fabric": fabric})
                self.worker_tracker.broadcast(start)

                # add fabric to worker_tracker.known_subscribers for hello tracking
                tw = TrackedWorker(fabric)
                tw.role = "subscriber"
                tw.active = True
                tw.start_time = start_ts
                tw.last_hello = start_ts
                self.worker_tracker.known_subscribers[fabric] = tw
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
            # on stop force restart ts delay by setting the 'last restart' to now.
            f.restart_ts = time.time()
            f.save()
        if fabric not in self.fabrics:
            logger.warn("stop requested for unknown fabric '%s'", fabric)
            return False
        elif self.fabrics[fabric]["process"] is not None:
            logger.debug("terminating fabric process '%s", fabric)
            terminate_process(self.fabrics[fabric]["process"])
            self.fabrics[fabric]["process"] = None
            # need to force all workers to flush their caches for this fabric
            stop = eptMsg(MSG_TYPE.FABRIC_STOP, data={"fabric": fabric})
            self.worker_tracker.broadcast(stop)
            # remove subscriber id from worker tracker known_subscribers
            self.worker_tracker.known_subscribers.pop(fabric, None)
            # remove fabric from auto-start before flushing messages
            if not f.exists() or not f.auto_start: 
                logger.debug("removing fabric '%s' from managed fabrics", fabric)
                self.fabrics.pop(fabric, None)
            else:
                self.fabrics[fabric]["waiting_for_retry"] = True
            # manager should flush all events from worker queues for the fabric instead of 
            # having worker perform the operation which could lead to race conditions. This needs
            # to happening in a different thread so it does not block hellos or other events 
            # received on the control thread.
            tmp = threading.Thread(target=self.worker_tracker.flush_fabric, args=(fabric,))
            tmp.daemon = True
            tmp.start()
            return True

    def check_fabric_processes(self):
        # check if each running fabric is still running. If not attempt to restart process
        # triggered by worker_tracker thread at WORKER_UDPATE_INTERVAL interval
        remove_list = []
        fabric_list = [(f, fab) for f, fab in self.fabrics.items()]
        for f, fab in fabric_list:
            hello_timeout = not ( f in self.worker_tracker.known_subscribers and \
                            self.worker_tracker.known_subscribers[f].active)
            if fab["process"] is not None and (hello_timeout or not fab["process"].is_alive()):
                # validate auto_start is enabled on the no-longer running fabric
                logger.warn("fabric %s no longer running (hello-timeout: %r)", f, hello_timeout)
                # set different error based on whether process is dead or hello timeout
                if hello_timeout:
                    self.stop_fabric(f, reason="subscriber heartbeat timeout")
                else:
                    self.stop_fabric(f, reason="subscriber no longer running")
                db_fab = Fabric.load(fabric=f)
                if db_fab.auto_start:
                    self.start_fabric(f, reason="auto restarting", restarting=True)
                else: 
                    remove_list.append(f)
            elif fab["process"] is None and fab["waiting_for_retry"]:
                self.start_fabric(f, reason="auto restarting", restarting=True)

        # stop tracking fabrics in remove list
        for f in remove_list: self.fabrics.pop(f, None)

    def increment_stats(self, queue, tx=False, count=1):
        # update stats queue
        with self.queue_stats_lock:
            if queue in self.queue_stats:
                if tx:
                    self.queue_stats[queue].total_tx_msg+= count
                    self.queue_stats["total"].total_tx_msg+= count
                else:
                    self.queue_stats[queue].total_rx_msg+= count
                    self.queue_stats["total"].total_rx_msg+= count

    def update_stats(self):
        """ update stats at regular interval """
        # monitor db health prior to db updates
        if not db_alive(self.db):
            logger.error("db no longer reachable/alive")
            raise_interrupt()
            return
        # update stats at regular interval for all queues
        for k, q in self.queue_stats.items():
            with self.queue_stats_lock:
                q.collect(qlen = self.redis.llen(k))
        
class WorkerTracker(object):
    # track list of active workers 
    def __init__(self, manager=None):
        self.manager = manager
        self.redis = self.manager.redis
        self.known_subscribers = {} # indexed by fabric-id
        self.known_workers = {}     # indexed by worker_id
        self.active_workers = {}    # list of active workers indexed by role
        self.update_interval = WORKER_UPDATE_INTERVAL # interval to check for new/expired workers
        self.update_thread = BackgroundThread(func=self.update_active_workers, count=0, 
                                            name="workerTracker", interval=self.update_interval)
        self.update_thread.daemon = True
        self.update_thread.start()

    def handle_hello(self, hello):
        # trigger appropriate worker/subscriber hello handler
        if hello.role == "subscriber":
            self.handle_subscriber_hello(hello)
        else:
            self.handle_worker_hello(hello)

    def handle_subscriber_hello(self, hello):
        # track hellos from subscribers.  Note, worker_id is the fabric name for this subscriber
        # subscribers are added automatically when monitor is started. There is no dynamic 
        # registraction of subscribers.  Therefore, we ignore unknown ids.
        if hello.worker_id not in self.known_subscribers:
            logger.debug("ignoring hello for unknown subscriber: %s", hello.worker_id)
        else:
            #logger.debug("received hello from %s", hello.worker_id)
            self.known_subscribers[hello.worker_id].last_hello = time.time()

    def handle_worker_hello(self, hello):
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
            logger.debug("new worker(%s) detected, waiting for activation period (%s sec)",
                    hello.worker_id, self.update_interval)
        else:
            self.known_workers[hello.worker_id].last_hello = time.time()

    def update_active_workers(self):
        # at a regular interval, check for new workers to add to active worker queue along with
        # removal of inactive workers.  This runs in a background thread independent of hello.  
        # Therefore, the time to detect a new worker is potential 2x update timer
        # This also executes fabric check on manager to ensure all subscriber processes are still
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
                if w.role not in self.active_workers: self.active_workers[w.role] = []
                self.active_workers[w.role].append(w)
                w.active = True
                new_workers = True
                # sort active workers by worker_id for deterministic ordering
                self.active_workers[w.role] = sorted(self.active_workers[w.role], 
                                                key=lambda w: int(re.sub("[^0-9]","",w.worker_id)))
                logger.info("new worker: %s, active_workers: [%s]", w, 
                                    ",".join([sw.worker_id for sw in self.active_workers[w.role]]))

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

        # inactive remove workers from known_workers and active_workers
        for w in remove_workers:
            logger.debug("removing worker from known_workers: %s", w)
            self.known_workers.pop(w.worker_id, None)
            if w.role in self.active_workers and w in self.active_workers[w.role]:
                logger.debug("removing worker from active_workers[%s]: %s", w.role, w)
                self.active_workers[w.role].remove(w)

            # TODO, rebalance work for this worker to a new worker - for now flush and restart
            for i, q in enumerate(w.queues):
                logger.debug("deleting work from queue: %s", q)
                with w.queue_locks[i]:
                    self.redis.delete(q)

        # if a worker has died, then trigger monitor restart for all fabrics
        if len(remove_workers)>0:
            inactive = "[%s]" % ", ".join([w.worker_id for w in remove_workers])
            # stop fabric (manager will restart when ready)
            for f in self.manager.fabrics.keys():
                self.manager.stop_fabric(f, reason="worker heartbeat timeout %s" % inactive)

        if len(remove_workers)>0 or new_workers:
            logger.info("total workers: %s", len(self.known_workers))


        # check hello from each subscriber. If any have timedout, set to inactive (manager func 
        # will restart any subscribers that are inactive)
        for sid, s in self.known_subscribers.items():
            if s.last_hello + HELLO_TIMEOUT < ts:
                logger.warn("subscriber timeout (last hello: %.3f) %s",ts-s.last_hello, s)
                # set to inactive
                s.active = False

        # trigger manager fabric processes check
        self.manager.check_fabric_processes()

    def send_bulk(self, msgs):
        """ receive list of tuples (_hash, msg) and enqueue to an available worker. 
            Each msg in bulk list must be of type eptMsgWork.  This will create sub bulk messages to
            reduce the blocking IO for redis calls.
            return boolean success
        """
        all_success = True
        work = {}   # dict indexed by worker_id and qnum with a tuple (worker, eptMsgBulk)
        for (_hash, msg) in msgs:
            if msg.role not in self.active_workers or len(self.active_workers[msg.role]) == 0:
                logger.warn("no available workers for role '%s'", msg.role)
                all_success = False
            else:
                index = _hash % len(self.active_workers[msg.role])
                worker = self.active_workers[msg.role][index]
                if msg.qnum >= len(worker.queues):
                    logger.warn("unable to enqueue work on worker %s, queue %s does not exist", 
                        worker.worker_id, msg.qnum)
                    all_success = False
                else:
                    if worker.worker_id not in work:
                        work[worker.worker_id] = {}
                    if msg.qnum not in work[worker.worker_id]:
                        work[worker.worker_id][msg.qnum] = (worker, eptMsgBulk())
                    work[worker.worker_id][msg.qnum][1].msgs.append(msg)
                    with worker.queue_locks[msg.qnum]:
                        worker.last_seq[msg.qnum]+= 1
                        msg.seq = worker.last_seq[msg.qnum]
                        self.manager.increment_stats(worker.queues[msg.qnum], tx=True)

        # send each message
        for worker_id in work:
            for qnum in work[worker_id]:
                (worker, tx_msg) = work[worker_id][qnum]
                # if there's only one message, then send that single message instead of bulk format
                if len(tx_msg.msgs) == 1:
                    tx_msg = tx_msg.msgs[0]
                else:
                    tx_msg.seq = tx_msg.msgs[-1].seq
                with worker.queue_locks[qnum]:
                    try:
                        #logger.debug("enqueue %s: %s", worker.queues[qnum], tx_msg)
                        self.redis.rpush(worker.queues[qnum], tx_msg.jsonify())
                    except Exception as e:
                        logger.error("failed to enqueue msg on queue %s: %s", worker.queues[qnum], 
                                        tx_msg)
                        all_success = False
        return all_success

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

    def flush_queue(self, fabric, q, lock=None):
        """ flush messages for provided fabric and redis queue """
        logger.debug("flushing %s from queue %s", fabric, q)
        # pull off all messages on the queue in single operation
        pl = self.redis.pipeline()
        pl.lrange(q, 0, -1)
        pl.delete(q)
        ret = []
        repush = []
        removed_count = 0
        if lock is not None:
            with lock: ret = pl.execute()
        else:
            ret = pl.execute()
        # inspect each message and if matching fabric discard, else push back onto queue
        if len(ret) > 0 and type(ret[0]) is list:
            logger.debug("inspecting %s msg from queue %s", len(ret[0]), q)
            for data in ret[0]:
                # need to reparse message and check fabric
                msg = eptMsg.parse(data) 
                # for eptMsgBulk it is currently safe to assume if the first msg is our fabric
                # then all messages will be our fabric
                if msg.msg_type == MSG_TYPE.BULK and len(msg.msgs)>0 and \
                    hasattr(msg.msgs[0], "fabric") and msg.msgs[0].fabric == fabric:
                    removed_count+=len(msg.msgs)
                elif hasattr(msg, "fabric") and msg.fabric == fabric:
                    removed_count+=1
                else:
                    repush.append(data)
            logger.debug("removed %s and repushing %s to queue %s",removed_count,len(repush),q)
            if len(repush) > 0:
                if lock is not None:
                    with lock: self.redis.rpush(q, *repush)
                else:
                    self.redis.rpush(q, *repush)
                logger.debug("repush completed")

    def flush_fabric(self, fabric, qnum=-1, role=None):
        # walk through all active workers and remove any work objects from queue for this fabric
        # note, this is a costly operation if the queue is significantly backed up...
        logger.debug("flush fabric '%s'", fabric)

        # flush work from this fabric for manager work queue if no specific role set
        if role is None:
            self.flush_queue(fabric, MANAGER_WORK_QUEUE)

        # flush work from active workers
        for r in self.active_workers:
            if role is None or r == role:
                for i, worker in enumerate(self.active_workers[r]):
                    if abs(qnum) > len(worker.queues):
                        logger.warn("unable to flush fabric for worker %s, qnum %s does not exist",
                                worker.worker_id, qnum)
                    else:
                        self.flush_queue(fabric, worker.queues[qnum], lock=worker.queue_locks[qnum])

    def get_worker_status(self, brief=False):
        # return list of dict representation of TrackedWorker objects along with queue_len list 
        # which is number of jobs currently in each queue
        status = []
        for wid, w in self.known_workers.items():
            js = w.to_json()
            js["queue_len"] = [get_queue_length(self.redis, q, accurate=not brief) for q in w.queues]
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

