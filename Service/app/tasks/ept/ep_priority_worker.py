"""
    Endpoint Priority Worker
    @author agossett@cisco.com
"""

from . import utils as ept_utils
from .node_manager import Node_Monitor
from .ep_job import EPJob
from Queue import Empty
import re, time, traceback

# setup logger for this package
import logging
logger = logging.getLogger(__name__)
ept_utils.setup_logger(logger)

class EPPriorityWorker(object):
    """ perform fabric-wide monitoring tasks that require updates to 
        EPWorkers
    """
    def __init__(self, txQ, rxQ, prQ, bcastQ, bcastPrQ, fabric, wid):
        self.txQ = txQ
        self.rxQ = rxQ
        self.prQ = prQ
        self.bcastQ = bcastQ      
        self.bcastPrQ = bcastPrQ   
        self.fabric = fabric
        self.wid = wid
        ept_utils.setup_logger(logger, "%s_ep_worker_%s.log" % (
            self.fabric, self.wid), quiet=True)
        ept_utils.logger = logger
        self.initialized = False
        self.monitor = None 
        self.monitor_disable = False

        # per-fabric config with defaults overwritten by setter
        self.worker_hello = 3.0          # worker hello ping interval
        self.worker_hello_multiplier = 4 # max amount of hellos to miss

        # job handlers and corresponding functions to execute. Update this 
        # object instead of modify the start function directly...
        self.job_handlers = {
            "handle_event": self.handle_event,
            "setter": self.setter,
            "init": self.init
        }

        # various intervals used by subscription and/or workers
        self.queue_interval = 0.1   

    def __repr__(self):
        return "%s:w%s" % (self.fabric, self.wid)

    def init(self, job):
        """ initialize priority worker - sends message on txQ on failure """
        if self.initialized: return
        logger.debug("intializing priority worker")
        success = False
        try:
            if not self.monitor_disable:
                self.monitor = Node_Monitor(self.fabric,self,
                    loggeroverride=logger)
            self.initialized = True
            success = True
        except Exception as e:
            logger.warn("exception occurred during initialization: %s" % e)
            job.key["error"] = "%s" % e

        # update job key with init succes
        job.key["success"] =  success

    def start(self):
        """ start listening on queue for jobs, put completed job object on
            txQ so parent knows it has completed
        """
        while True:
            job = None
            while job is None:
                # process all messages from prQ before checking rxQ
                try: job = self.prQ.get_nowait()
                except Empty:
                    try: job = self.rxQ.get_nowait()
                    except Empty:
                        time.sleep(self.queue_interval)
            try:
                if job.action == "hello":
                    self.handle_hello()
                else:
                    logger.debug("[%s] got job %s [prQ:%s,rxQ:%s]" % (
                        self,job,self.prQ.qsize(),self.rxQ.qsize()))
                    if job.action in self.job_handlers:
                        self.job_handlers[job.action](job)
                    else:
                        logger.error("[%s] unknown job action %s" % (self,job))
            except Exception as e:
                logger.error(traceback.format_exc())
            self.txQ.put(job)
            try:
                if job.action!="hello":
                    logger.debug("[%s] finished job %s [prQ:%s,rxQ:%s]" % (
                        self,job,self.prQ.qsize(),self.rxQ.qsize()))
            except Exception as e: pass

    def setter(self, job):
        """ since worker is running as child process, we need a way for parent
            to update/set variables on this child process.  Since we already 
            have queuing process available, easiest way is to update setting
            via 'setter' job.  This function receives a dictionary 'data' with
            attributes of this object to update
        """
        data = job.data
        logger.debug("[%s] setter: %s" % (self, data))
        try:
            for k in data:
                # allow any local variable to be updated...
                if not hasattr(self, k):
                    logger.debug("ignoring update for attribute: %s" % k)
                else:
                    setattr(self, k, data[k])
        except Exception as e:
            logger.error(traceback.format_exc()) 
            return

    def extend_hello(self, time=0):
        """ send request to parent to temporarily extend the hello time 
            the extended time is max timeout + requested time
        """
        time = float(time) + self.worker_hello*self.worker_hello_multiplier
        self.txQ.put(EPJob("extend_hello", {}, data= {"time": time}))

    def requeue_job(self, jobs):
        """ send requeue job with list of jobs to be requeue to parent """
        # allow calling function to provide single job or list of jobs
        if isinstance(jobs, EPJob): jobs = [jobs]
        logger.debug("sending requeue job: %s" % jobs)
        self.txQ.put(EPJob("requeue", {}, data={"jobs":jobs}))

    def restart_subscription(self, reason=None):
        """ send message to parent to restart subscriptions """
        logger.debug("restart subscription request: %s" % reason)
        self.txQ.put(EPJob("inform", {}, data= {"reason": "%s" % reason,
            "rc": ept_utils.RC_SUBSCRIPTION_RESTART}))

    def clear_worker_cache(self, cache):
        """ put message on bcastPrQ to clear a specific cache """
        logger.debug("sending on bcastPrQ clear cache: %s" % cache)
        for q in self.bcastPrQ:
            q.put(EPJob("clear_cache", {}, data = {"cache":cache} ))

    def handle_hello(self):
        """ hello from parent triggers hello check on all worker processes
            send broadcast hello and return
        """
        for q in self.bcastPrQ: q.put(EPJob("hello",{})) 

    def handle_event(self, job):
        """ handle event from various subscriptions.  Key must contain:
                classname - classname of object that triggered event
                event - event json object
        """
        key = job.data
        if not self.initialized:
            logger.error("priority worker not yet successfully initialized")
            return
        if self.monitor_disable:
            logger.warn("monitor disabled")
            return
        if "classname" not in key or "event" not in key:
            logger.error("classname and/or event missing from key: %s" % key)
            return
        if key["classname"] == "namedEvent":
            self.monitor.handle_name_event(key["event"])
        elif key["classname"] == "subnetEvent":
            self.monitor.handle_subnet_event(key["event"])
        elif key["classname"] == "vpcRsVpcConf":
            self.monitor.handle_vpcRsVpcConf(key["event"])

        elif key["classname"] == "fabricNode":
            # fabricNode returns which node changed and current status
            # which needs to be acted on in the fabric
            ret = self.monitor.handle_fabricNode(key["event"])
            if ret is not None:
                logger.debug("received %s from handle_fabricNode" % ret)
                if "node" in ret and ret["node"] is not None and \
                    "status" in ret and ret["status"] is not None \
                    and "pod" in ret and ret["pod"] is not None:
                    self.requeue_job(EPJob("watch_node",{},data=ret))
                else:
                    logger.debug("invalid node/status returned")

        elif key["classname"] == "fabricProtPol":
            self.monitor.handle_fabricProtPol(key["event"])
        elif key["classname"] == "fabricExplicitGEp":
            self.monitor.handle_fabricExplicitGEp(key["event"])
        else:
            logger.warn("unexpected event received for class(%s): %s" % (
                key["classname"], key["event"]))

