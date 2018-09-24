
from ... utils import get_app_config
from ... utils import get_db
from . common import wait_for_db
from . common import wait_for_redis
from . common import HELLO_INTERVAL
from . common import WORKER_CTRL_CHANNEL
from . ept_msg import MSG_TYPE
from . ept_msg import eptMsg
from . ept_msg import eptMsgHello
from . ept_queue_stats import eptQueueStats

import json
import logging
import re
import redis
import threading
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class eptWorker(object):
    
    def __init__(self, worker_id, role):
        self.worker_id = "%s" % worker_id
        self.role = role
        self.app_config = get_app_config()
        self.db = get_db()
        self.redis = redis.StrictRedis(host=self.app_config["REDIS_HOST"], 
                            port=self.app_config["REDIS_PORT"], db=self.app_config["REDIS_DB"])

        # broadcast hello for any managers (registration and keepalives)
        self.hello_thread = None
        # update stats db at regular interval
        self.stats_thread = None

        # queues that this worker will listen on 
        self.queues = ["q0_%s" % self.worker_id, "q1_%s" % self.worker_id]
        self.queue_stats_lock = threading.Lock()
        self.queue_stats = {
            "q0_%s" % self.worker_id: eptQueueStats.load(proc=self.worker_id, 
                                                    queue="q0_%s" % self.worker_id),
            "q1_%s" % self.worker_id: eptQueueStats.load(proc=self.worker_id, 
                                                    queue="q1_%s" % self.worker_id),
            WORKER_CTRL_CHANNEL: eptQueueStats.load(proc=self.worker_id,
                                                    queue=WORKER_CTRL_CHANNEL),
            "total": eptQueueStats.load(proc=self.worker_id, queue="total"),
        }
        # initialize stats counters
        for k, q in self.queue_stats.items():
            q.init_queue()

        self.start_time = time.time()
        self.hello_msg = eptMsgHello(self.worker_id, self.role, self.queues, self.start_time)
        self.hello_msg.seq = 0

    def __repr__(self):
        return self.worker_id

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        try:
            wait_for_redis(self.redis)
            wait_for_db(self.db)
            self.send_hello()
            self.update_stats()
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        finally:
            if self.hello_thread is not None:
                self.hello_thread.cancel()
            if self.stats_thread is not None:
                self.stats_thread.cancel()

    def _run(self):
        """  start hello thread for registration notifications/keepalives and wait on work """
        # first check/wait on redis and mongo connection, then start hello thread
        logger.debug("[%s] listening for jobs on queues: %s", self, self.queues)
        while True: 
            logger.debug("big sleep.... %s", time.sleep(60))
            (q, data) = self.redis.blpop(self.queues)
            if q in self.queue_stats:
                self.increment_stats(q, tx=False)
            try:
                msg = eptMsg.parse(data) 
                logger.debug("[%s] msg on q(%s): %s", self, q, msg)
                if msg.msg_type == MSG_TYPE.FLUSH_FABRIC.value:
                    self.flush_fabric(fabric=msg.data["fabric"])

            except Exception as e:
                logger.debug("failure occurred on msg from q: %s, data: %s", q, data)
                logger.error("Traceback:\n%s", traceback.format_exc())

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

    def send_hello(self):
        """ send hello/keepalives at regular interval, this also serves as registration """
        self.hello_msg.seq+= 1
        logger.debug(self.hello_msg)
        self.redis.publish(WORKER_CTRL_CHANNEL, self.hello_msg.jsonify())
        self.increment_stats(WORKER_CTRL_CHANNEL, tx=True)
        self.hello_thread = threading.Timer(HELLO_INTERVAL, self.send_hello)
        self.hello_thread.daemon = True
        self.hello_thread.start()

    def flush_fabric(self, fabric):
        """ flush all work within queues for provided fabric then enqueue work back to list """
        logger.debug("[%s] flush fabric", self, fabric)






