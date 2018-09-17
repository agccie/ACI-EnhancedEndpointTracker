
from ... utils import setup_logger
from ... utils import get_app_config
from ... utils import get_db
from . common import HELLO_CHANNEL
from . common import HELLO_INTERVAL
from . ep_job import EPJob

import argparse
import json
import logging
import redis
import threading
import time
import traceback
import sys

# module level logging
logger = logging.getLogger(__name__)


class EPWorker(object):
    
    def __init__(self, worker_id):
        self.worker_id = "%s" % worker_id
        self.app_config = get_app_config()
        self.db = get_db()
        self.redis = redis.StrictRedis(host=self.app_config["REDIS_HOST"], 
                            port=self.app_config["REDIS_PORT"], db=self.app_config["REDIS_DB"])

        # set once instead of executing json dumps every hello
        self.hello_msg = json.dumps({"type":"hello", "worker":self.worker_id})
        self.hello_thread = threading.Thread(target=self.send_hello)
        self.hello_thread_kill = False  # kill signal for unexpected main thread exit

    def __repr__(self):
        return self.worker_id

    def redis_alive(self):
        """ return true if able to connect and execute command against redis db """
        try:
            if self.redis.dbsize() >= 0:
                logger.debug("successfully connected to redis db")
                return True
        except Exception as e:
            logger.debug("failed to connect to redis db: %s", e)
        return False

    def db_alive(self):
        """ return true if able to connect and execute command agaist mongo db """
        try:
            if len(self.db.collection_names()) >= 0:
                logger.debug("successfully connected to mongo db")
                return True
        except Exception as e:
            logger.debug("failed to connect to mongo db: %s", e)
        return False

    def send_hello(self):
        """ send hello/keepalives at regular interval, this also serves as registration """
        while True:
            if self.hello_thread_kill: return
            logger.debug("[%s] hello", self)
            self.redis.publish(HELLO_CHANNEL,EPJob("hello",{"worker":self.worker_id}).jsonify())
            if self.hello_thread_kill: return
            time.sleep(HELLO_INTERVAL)

    def run(self):
        """  start hello thread for registration notifications/keepalives and wait on work """
        # first check/wait on redis and mongo connection
        while not self.redis_alive(): time.sleep(1)
        while not self.db_alive(): time.sleep(1)
        self.hello_thread.start()
        
        queues = ["p_%s" % self.worker_id, "w_%s" % self.worker_id]
        logger.debug("[%s] listening for jobs on queues: %s", self, queues)
        while True: 
            (q, data) = self.redis.blpop(queues)
            try:
                job = EPJob.parse(data) 
                logger.debug("[%s] job on q(%s): %s", self, q, job.keystr)
            except Exception as e:
                logger.debug("failure occurred on job from q: %s, data: %s", q, data)
                logger.error("Traceback:\n%s", traceback.format_exc())

if __name__ == "__main__":

    desc = """ worker node """
    parser = argparse.ArgumentParser(description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    parser.add_argument("--id", dest="worker_id", required=True, help="unique id for this worker")
    parser.add_argument("--stdout", dest="stdout", action="store_true", help="send logs to stdout")
    args = parser.parse_args()

    stdout = args.stdout
    fname="worker_%s" % args.worker_id
    debug_modules = []
    setup_logger(logger,fname=fname,stdout=stdout,quiet=True,thread=True)
    for l in debug_modules:
        setup_logger(logging.getLogger(l), fname=fname, stdout=stdout, thread=True)

    try:
        w = EPWorker(args.worker_id)
        w.run()
        logger.error("worker %s unexpected ended", w.worker_id)
    except (Exception, SystemExit, KeyboardInterrupt) as e:
        logger.error("Traceback:\n%s", traceback.format_exc())
        if w.hello_thread.is_alive():
            w.hello_thread_kill = True
            w.hello_thread.join()
        sys.exit(1)

