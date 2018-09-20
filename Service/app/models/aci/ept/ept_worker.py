
from ... utils import get_app_config
from ... utils import get_db
from . common import wait_for_db
from . common import wait_for_redis
from . common import HELLO_INTERVAL
from . common import WORKER_CTRL_CHANNEL
from . ept_msg import eptMsg
from . ept_msg import eptMsgHello
from . ept_stats import eptWorkerQueueStats

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

        # queues that this worker will listen on 
        self.queues = ["q0_%s" % self.worker_id, "q1_%s" % self.worker_id]
        self.queue_stats = {
            "q0_%s" % self.worker_id: eptWorkerQueueStats("q0_%s" % self.worker_id, 0),
            "q1_%s" % self.worker_id: eptWorkerQueueStats("q1_%s" % self.worker_id, 1),
        }
        self.start_time = time.time()
        self.hello_msg = eptMsgHello(self.worker_id, self.role, self.queues, self.start_time)
        self.hello_msg.seq = 0

    def __repr__(self):
        return self.worker_id

    def send_hello(self):
        """ send hello/keepalives at regular interval, this also serves as registration """
        self.hello_msg.seq+= 1
        logger.debug(self.hello_msg)
        self.redis.publish(WORKER_CTRL_CHANNEL, self.hello_msg.jsonify())
        self.hello_thread = threading.Timer(HELLO_INTERVAL, self.send_hello)
        self.hello_thread.daemon = True
        self.hello_thread.start()

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        try:
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        finally:
            if self.hello_thread is not None:
                self.hello_thread.cancel()

    def _run(self):
        """  start hello thread for registration notifications/keepalives and wait on work """
        # first check/wait on redis and mongo connection, then start hello thread
        wait_for_redis(self.redis)
        wait_for_db(self.db)

        logger.debug("[%s] listening for jobs on queues: %s", self, self.queues)
        self.send_hello()
        while True: 
            (q, data) = self.redis.blpop(self.queues)
            try:
                msg = eptMsg.parse(data) 
                logger.debug("[%s] msg on q(%s): %s", self, q, msg)

            except Exception as e:
                logger.debug("failure occurred on msg from q: %s, data: %s", q, data)
                logger.error("Traceback:\n%s", traceback.format_exc())




