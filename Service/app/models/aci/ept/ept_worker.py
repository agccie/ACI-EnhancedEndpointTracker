
from ... utils import get_app_config
from ... utils import get_db
from . common import HELLO_CHANNEL
from . common import HELLO_INTERVAL
from . common import wait_for_db
from . common import wait_for_redis
from . ept_msg import EPTMsg
from . ept_msg import EPTMsgHello
from . ept_stats import EPTWorkerQueueStats

import json
import logging
import re
import redis
import threading
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class EPTWorker(object):
    
    def __init__(self, worker_id, role):
        self.worker_id = "%s" % worker_id
        self.role = role
        self.app_config = get_app_config()
        self.db = get_db()
        self.redis = redis.StrictRedis(host=self.app_config["REDIS_HOST"], 
                            port=self.app_config["REDIS_PORT"], db=self.app_config["REDIS_DB"])

        # broadcast hello for any managers (registration and keepalives)
        self.hello_thread = threading.Thread(target=self.send_hello)
        self.hello_thread_kill = False  # kill signal for unexpected main thread exit

        # queues that this worker will listen on 
        self.queues = ["p_%s" % self.worker_id, "w_%s" % self.worker_id]
        self.queue_stats = {
            "p_%s" % self.worker_id: EPTWorkerQueueStats("p_%s" % self.worker_id, 0),
            "w_%s" % self.worker_id: EPTWorkerQueueStats("w_%s" % self.worker_id, 1),
        }
        self.start_time = time.time()
        self.hello_msg = EPTMsgHello(self.worker_id, self.role, self.queues, self.start_time)

    def __repr__(self):
        return self.worker_id

    def send_hello(self):
        """ send hello/keepalives at regular interval, this also serves as registration """
        while True:
            if self.hello_thread_kill: return
            self.hello_msg.seq+= 1
            logger.debug(self.hello_msg)
            self.redis.publish(HELLO_CHANNEL, self.hello_msg.jsonify())
            time.sleep(HELLO_INTERVAL)

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        try:
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
            if self.hello_thread.is_alive():
                self.hello_thread_kill = True
                self.hello_thread.join()

    def _run(self):
        """  start hello thread for registration notifications/keepalives and wait on work """
        # first check/wait on redis and mongo connection, then start hello thread
        wait_for_redis(self.redis)
        wait_for_db(self.db)
        self.hello_thread.start()
        
        logger.debug("[%s] listening for jobs on queues: %s", self, self.queues)
        while True: 
            (q, data) = self.redis.blpop(self.queues)
            try:
                job = EPTMsg.parse(data) 
                logger.debug("[%s] job on q(%s): %s", self, q, job.keystr)

            except Exception as e:
                logger.debug("failure occurred on job from q: %s, data: %s", q, data)
                logger.error("Traceback:\n%s", traceback.format_exc())
            finally:
                self.hello_thread_kill = True



