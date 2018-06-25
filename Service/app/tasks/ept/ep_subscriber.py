"""
    Endpoint Subscriber
    @author agossett@cisco.com
"""

from . import utils as ept_utils
from .ep_job import EPJob
from .ep_worker import EPWorker, ep_get_delete_jobs
from .ep_priority_worker import EPPriorityWorker
import re, time, traceback
from multiprocessing import Process as mProcess
from multiprocessing import Queue as mQueue
from Queue import Empty
from pymongo import ASCENDING as py_ascend

# setup logger for this package
import logging
logger = logging.getLogger(__name__)
ept_utils.setup_logger(logger)

class EPSubscriber(object):
    """ APIC subscriptions for all EPM monitors """
    
    def __init__(self, fabric, overlay_vnid):
        self.fabric = fabric
        self.overlay_vnid = overlay_vnid
        # setup logging for this fabric
        ept_utils.setup_logger(logger, "%s_ep_manager.log" % self.fabric)
        ept_utils.logger = logger
        self.app = ept_utils.get_app()
        self.session = None 

        self.next_worker = 0    # next free worker id to dispatch job
        self.pending_jobs = 0   # total number of pending jobs over all workers
        self.workers = {}       # track each worker and thier message queues
                                # txQ = queue for sending messages to worker
                                # rxQ =queue for receiving messages from worker
        self.requeues = []      # list of requeues to service
        self.requeues_inservice = False
        self.rebuild_jobs = []  # list of epm events jobs provided at rebuild
                                # that need to be enqueued

        self.pworker = None     # dedicated priority queue worker
        self.wworker = None    # dedicated watch worker for transit events
        # disable flags only changed by simulator
        self.wworker_disable = False    # watch worker
        self.pworker_disable = False    # priority worker
        self.monitor_disable = False    # pworker node_monitor

        self.all_workers = []   # list of all workers including self.workers,
                                # self.pworker, and self.wworker

        self.jobs = {}          # dict of active jobs indexed by key

        # max number of duplicate keys for an endpoint for a single move
        # considering large BD in flood mode where host move is seen on all
        # leaves:
        #   (delete+create)*(epmIpEp + Rs + epmMacEp)*(number of leafs)
        #   2*3*(200 leafs in large L2 fabric) = 1200
        self.max_key_count = 1200
        # number of enqueue failures (key count exceeds max key count) to
        # trigger flush of pending jobs in worker queue and notify of failure
        self.enqueue_fail_threshold = 1 

        self.worker_hello = 3.0          # worker hello ping interval
        self.worker_hello_multiplier = 4 # max amount of hellos to miss

        # trust subscription flag to determine whether each event requires 
        # ep_refresh or if event can be inserted directly into database
        self.trust_subscription = True

        # per-fabric ep/apic config
        self.conf = ept_utils.get_apic_config(fabric)
        if self.conf is None:
            logger.warn("failed to read per-fabric config, using defaults") 
            self.conf = {}

        # local settings from apic_config with default values
        self.max_ep_events = self.conf.get("max_ep_events", 64)
        self.max_workers = self.conf.get("max_workers", 6)
        self.max_jobs = self.conf.get("max_jobs", 65536)
        self.analyze_move = self.conf.get("analyze_move", True)
        self.analyze_stale = self.conf.get("analyze_stale", True)
        self.analyze_offsubnet = self.conf.get("analyze_offsubnet", True)
        self.auto_clear_stale = self.conf.get("auto_clear_stale", False)
        self.auto_clear_offsubnet = self.conf.get("auto_clear_offsubnet", False)
        self.notify_stale_syslog = self.conf.get("notify_stale_syslog", False)
        self.notify_stale_email = self.conf.get("notify_stale_email", False)
        self.notify_move_syslog = self.conf.get("notify_move_syslog", False)
        self.notify_move_email = self.conf.get("notify_move_email", False)
        self.notify_offsubnet_syslog = self.conf.get("notify_offsubnet_syslog",
            False)
        self.notify_offsubnet_email = self.conf.get("notify_offsubnet_email", 
            False)
        self.notify_email = self.conf.get("email_address", "")
        self.notify_syslog = self.conf.get("syslog_server", "")
        self.notify_syslog_port = self.conf.get("syslog_port", 514)

        # various intervals used by subscription and/or workers
        self.controller_interval = 1.0
        self.queue_interval = 0.1   
        self.transitory_delete_time = 3.0  
        self.transitory_stale_time = 30.0
        self.transitory_xr_stale_time = 300.0
        self.transitory_offsubnet_time = 30.0

    def start_workers(self):
        """ start worker processes """

        # setter config
        setter_conf = {}
        for attr in ["analyze_move", "analyze_stale", "analyze_offsubnet",
            "auto_clear_stale","auto_clear_offsubnet",
            "notify_stale_syslog", "notify_stale_email",
            "notify_offsubnet_syslog", "notify_offsubnet_email",
            "notify_move_syslog", "notify_move_email", "notify_email",
            "notify_syslog", "notify_syslog_port", "max_ep_events",
            "worker_hello", "worker_hello_multiplier",
            "trust_subscription", "queue_interval", "transitory_delete_time",
            "transitory_stale_time", "transitory_xr_stale_time", 
            "transitory_offsubnet_time",
            "monitor_disable"]:
            if hasattr(self, attr): setter_conf[attr] = getattr(self, attr)

        # manually stop any/all workers before starting workers
        self.stop_workers()
        self.all_workers = []
        self.workers = {}
        for wid in range(self.max_workers):
            logger.debug("starting worker id(%s)" % wid)
            w = {"wid": wid, "txQ": mQueue(), "rxQ": mQueue(), "prQ": mQueue(),
                "last_hello": 0}
            p = mProcess(target=start_ep_worker, kwargs={
                "wid": w["wid"],
                "txQ": w["rxQ"], # swap tx/rx queue from worker perspective
                "rxQ": w["txQ"],
                "prQ": w["prQ"],
                "fabric": self.fabric, 
                "overlay_vnid": self.overlay_vnid
            })
            w["process"] = p
            # enqueue any specific variables for this worker via job
            w["txQ"].put(EPJob("setter", {}, data=setter_conf))
            p.start()
            self.workers[wid] = w
            self.all_workers.append(w)

        # setup/start watch worker
        if not self.wworker_disable:
            logger.debug("starting watcher worker")
            self.wworker = {"wid":"watcher","txQ":mQueue(),"rxQ":mQueue(),
                "prQ":mQueue(), "last_hello":0}
            p = mProcess(target=start_ep_worker, kwargs={
                "wid": self.wworker["wid"],
                "txQ": self.wworker["rxQ"], # swap tx/rx queue
                "rxQ": self.wworker["txQ"],
                "prQ": self.wworker["prQ"],
                "fabric": self.fabric, 
                "overlay_vnid": self.overlay_vnid
            })
            self.wworker["process"] = p
            self.wworker["txQ"].put(EPJob("setter", {}, data=setter_conf))
            p.start()
            self.all_workers.append(self.wworker)
        else:
            logger.debug("skipping watch worker")

        if self.pworker_disable: 
            logger.debug("skipping priority worker")
            return

        # setup/start priority queue worker
        logger.debug("starting priority worker")
        bcastQ = []
        bcastPrQ = []
        for wid in self.workers:
            bcastQ.append(self.workers[wid]["txQ"])
            bcastPrQ.append(self.workers[wid]["prQ"])
        if not self.wworker_disable:
            bcastQ.append(self.wworker["txQ"])
            bcastPrQ.append(self.wworker["prQ"])
        self.pworker = {"wid": "pri", "txQ": mQueue(), "rxQ": mQueue(), 
            "prQ": mQueue(), "last_hello": 0}
        p = mProcess(target=start_ep_priority_worker, kwargs={
            "wid": self.pworker["wid"],
            "txQ": self.pworker["rxQ"], # swap tx/rq queue 
            "rxQ": self.pworker["txQ"],
            "prQ": self.pworker["prQ"],
            "bcastQ": bcastQ,
            "bcastPrQ": bcastPrQ,
            "fabric": self.fabric,
        })
        self.pworker["txQ"].put(EPJob("setter", {}, data=setter_conf))
        self.pworker["txQ"].put(EPJob("init", {}))
        self.pworker["process"] = p
        p.start()
        self.all_workers.append(self.pworker)
        
        # wait for priority worker setter and init job to successfully complete
        job = None
        try:
            job_setter = self.pworker["rxQ"].get(True, 3.0) 
            job = self.pworker["rxQ"].get(True, 3.0) 
        except Empty: pass
        if job is None or "success" not in job.key or not job.key["success"]:
            err = "failed to initialize priority worker"
            if job is not None and "error" in job.key: err = job.key["error"]
            logger.warn(err)
            self.stop_workers()
            raise Exception(err)
        else:
            logger.debug("successfully initialized priority worker")


    def stop_workers(self, delay=0):
        """ stop worker processes with configurable delay """
        if delay > 0: time.sleep(delay)
        for w in self.all_workers:
            p = w["process"]
            wid = w["wid"]
            logger.debug("killing worker id(%s)" % (wid))
            ept_utils.terminate_process(p)

    def subscribe_to_objects(self):
        """ subscribe to objects 
            create session to apic for all epm objects
        """
        # define subscription interests
        interests = {
            "epmMacEp":{"callback": self.handle_epmMacEp}, 
            "epmIpEp":{"callback": self.handle_epmIpEp},
            "epmRsMacEpToIpEpAtt":{"callback":self.handle_epmRsMacEpToIpEpAtt},
            "fabricProtPol":{"callback":self.handle_fabricProtPol},
            "fabricExplicitGEp":{"callback":self.handle_fabricExplicitGEp},
            "vpcRsVpcConf":{"callback":self.handle_vpcRsVpcConf},
            "fabricNode":{"callback": self.handle_fabricNode},
            "fvCtx": {"callback": self.handle_name_event},
            "fvBD": {"callback": self.handle_name_event},
            "fvSvcBD": {"callback": self.handle_name_event},
            "fvEPg": {"callback": self.handle_name_event},
            "fvRsBd": {"callback": self.handle_name_event},
            "vnsRsEPpInfoToBD": {"callback": self.handle_name_event},
            "l3extExtEncapAllocator": {"callback": self.handle_name_event},
            "fvSubnet": {"callback": self.handle_subnet_event},
            "fvIpAttr": {"callback": self.handle_subnet_event},
        }
        try:
            while 1:
                # start worker processes
                self.start_workers()
                
                # enqueue initial rebuild jobs created from stage_ep_history_db
                while len(self.rebuild_jobs)>0:
                    self.enqueue_job(self.rebuild_jobs.pop(0))

                # override max_key_count if trust_subscription is disabled
                if not self.trust_subscription:
                    self.max_key_count = 64

                # start subscriptions
                ept_utils.add_fabric_event(self.fabric, "Running", "")
                rc = ept_utils.subscribe(self.fabric, interests=interests, 
                    checker=check_apic_health, 
                    controller=self.control_subscription,
                    controller_interval=self.controller_interval)
                # restart subscription if we see a stateful subscription close
                if rc == ept_utils.RC_SUBSCRIPTION_CLOSE:
                    self.stop_workers(delay=0.1)
                    logger.warn("received subscripton close, re-subscribe")
                    ept_utils.add_fabric_event(self.fabric, "Re-initializing",
                        "Restarting subscription")
                    continue
                elif rc == ept_utils.RC_SUBSCRIPTION_FAIL:
                    logger.warn("received subscription fail")
                    ept_utils.add_fabric_event(self.fabric, "Restarting",
                        "APIC subscription failed")
                else:
                    logger.warn("unexpected subscription rc: %s" % rc)
                break
        finally:
            # if subscriptions unexpectedly close, stop workers
            logger.debug("subscription unexpectedly ended")
            self.stop_workers(delay=0.1)

    def control_subscription(self):
        """ control_subscription called at regular interval from subscription 
            function.  for ep_subscriber, we need to do the following

            1) check all workers are alive by executing check_worker_hello

            2) check priority worker queue
            jobs enqueued on priority worker are put on rxQ when completed.
            in addition, priority worker may enqueue a job with "inform" 
            action which is used to alert this thread (parent) of return
            code that needs to be returned to subscription process.  It can
            also return a 'requeue' job for various work that needs to be
            requeued to normal workers.

        """
        try:    
            # no-op if priority worker is disabled
            if self.pworker_disable: return

            # check all worker's hello
            self.check_worker_hello()

            # check return code from priority worker
            ts = time.time()
            while True:
                job = self.pworker["rxQ"].get_nowait()
                if job.action == "hello": self.pworker["last_hello"] = ts
                elif job.action == "inform" and "rc" in job.data:
                    logger.debug("rx completed job from priority worker:%s"%(
                        job))
                    return job.data["rc"]
                elif job.action == "requeue":
                    logger.debug("received requeue jobs from 'pri'")
                    self.requeues.append(job)
                elif job.action == "extend_hello": 
                    self.extend_hello(job, self.pworker)
                else:
                    logger.debug("ignoring ret job %s from 'pri'" % job)
        except Empty as e: pass
        # if there are any requeue jobs, execute them
        self.requeue_jobs()

    def check_worker_hello(self):
        """ check hello times for all workers and if any have failed to force
            hard restart.  This is done by enqueuing a 'hello' job on the 
            priority worker which in turn sends hello job to all other workers.
            Each worker completes the hello process and puts back on its rxQ
            which is seen by this object. If hello has not been received within
            threshold then assume process has died.
            Returns boolean success if all workers are alive
        """

        # service worker queues
        self.refresh_workers()

        ts = time.time()
        # check hello from all workers
        for w in self.all_workers:
            if w["last_hello"]>0 and ts > w["last_hello"] + (
                self.worker_hello*self.worker_hello_multiplier):
                logger.warn("worker %s hello timeout (time:%f, last:%f)" % (
                    w["wid"], ts, w["last_hello"]))
                ept_utils.restart_fabric(self.fabric, 
                    reason="worker(%s) hello timeout" % w["wid"])
                return False

        # enqueue hello to priority worker
        if not self.pworker_disable:
            if ts >= self.pworker["last_hello"] + self.worker_hello:
                self.pworker["prQ"].put(EPJob("hello",{}))

        return True

    def extend_hello(self, job, worker):
        """ allow a worker to request temporary hello extension """
        if "time" in job.data:
            worker["last_hello"] = time.time() + job.data["time"]
            logger.debug("extending '%s' hello by %s: %f" % (
                worker["wid"], job.data["time"], worker["last_hello"]))
        else:
            logger.warn("invalid data for extend_hello: %s" % job.data)

    def refresh_workers(self):
        """  each worker puts key of job it has completed on this object's
        per-worker rxQ. Before any job is enqueued, we need to read through 
        rxQ for each worker to update completed jobs and pointers to next
        available worker
        """
        self.pending_jobs = 0
        self.next_worker = None
        min_count = 0
        ts = time.time()
        for wid in self.workers:
            w = self.workers[wid]
            qc = w["txQ"].qsize()
            self.pending_jobs+= qc
            if self.next_worker is None or qc < min_count:
                self.next_worker = wid
                min_count = qc
            try:
                while True:
                    job = w["rxQ"].get_nowait()
                    if job.action == "hello": w["last_hello"] = ts
                    elif job.keystr in self.jobs:
                        self.jobs[job.keystr]["count"]-=1
                        logger.debug("job complete on(%s) count left(%s):%s"% (
                            self.jobs[job.keystr]["wid"],
                            self.jobs[job.keystr]["count"], job.keystr))
                        if self.jobs[job.keystr]["count"]<=0:
                            self.jobs.pop(job.keystr,None)
                    elif job.action == "requeue":
                        logger.debug("received requeue jobs from wid(%s)"%wid)
                        self.requeues.append(job)
                    elif job.action == "extend_hello": self.extend_hello(job, w)
                    elif "watch" in job.action: pass
                    else:
                        logger.debug("ignoring ret job %s from worker '%s'"%(
                            job,wid))
            except Empty as e: pass       

        # service watch worker queue (only checking for hello right now)
        if not self.wworker_disable:
            try:
                while True:
                    job = self.wworker["rxQ"].get_nowait()
                    if job.action == "hello": self.wworker["last_hello"] = ts
                    elif job.action == "requeue": 
                        logger.debug("received requeue jobs from watcher")
                        self.requeues.append(job)
                    elif job.action == "extend_hello": 
                        self.extend_hello(job, self.wworker)
                    elif "watch" in job.action: pass
                    else:
                        logger.debug("ignoring ret job %s from 'watcher'" % job)
            except Empty as e: pass

        # if there are any requeue jobs, execute them
        self.requeue_jobs()

    def requeue_jobs(self):
        """ requeues all jobs in self.requeues list
            Note, a requeue job has 'jobs' list in data attribute allow to a 
            single requeue to repesent multiple jobs
        """
        if len(self.requeues)==0: return
        # if already servicing requeues, then ignore request new request
        if self.requeues_inservice: 
            logger.debug("requeue already in service, ignoring request")
            return
        logger.debug("starting requeue of %s batch jobs" % len(self.requeues))
        self.requeues_inservice = True
        
        while len(self.requeues)>0:
            job = self.requeues.pop(0)
            if "jobs" in job.data:
                for j in job.data["jobs"]:
                    if isinstance(j, EPJob): self.enqueue_job(j)
                    else: logger.warn("requeue %s is not an EPJob"%j)
        self.requeues_inservice = False
        logger.debug("requeue jobs completed")

    def enqueue_priority_job(self, job):
        """ add a job to priority worker. """
        if self.pworker_disable:
            logger.debug("ignoring, pworker_disabled")
            return False
        pending = self.pworker["txQ"].qsize()
        if pending > self.max_jobs:
            logger.error("pending jobs(%d) exceeds max threshold(%d)" % (
                pending, self.max_jobs))
            # force a restart since this is critical error
            ept_utils.restart_fabric(self.fabric, 
                "priority job count exceeds max threshold %s" % self.max_jobs)
            return False
        logger.debug("enqueue on priority worker job:%s [txQ:%s][rxQ:%s]" % (
            job, pending, self.pworker["rxQ"].qsize()))
        self.pworker["txQ"].put(job)
        return True

    def enqueue_watch_job(self, job):
        """ add a job to watch worker """
        if self.wworker_disable:
            logger.debug("ignoring, wworker_disabled")
            return False
        pending = self.wworker["txQ"].qsize()
        if pending > self.max_jobs:
            logger.error("pending jobs(%d) exceeds max threshold(%d)" % (
                pending, self.max_jobs))
            # force a restart since this is critical error
            ept_utils.restart_fabric(self.fabric, 
                "watcher job count exceeds max threshold %s" % self.max_jobs)
            return False
        logger.debug("enqueue on watch worker job:%s [txQ:%s][rxQ:%s]" % (
            job, pending, self.wworker["rxQ"].qsize()))
        self.wworker["txQ"].put(job)
        return True

    def enqueue_job(self, job):
        """ add a job to a single workers queue. If job is duplicate key of a
        currently active job, then enqueue into the same worker as previous
        job up to max_key_count.  Else, choose the worker with least
        number of jobs in queue as set by self.next_worker
        """
        self.refresh_workers()

        if "watch_" in job.action: return self.enqueue_watch_job(job)
        if self.pending_jobs > self.max_jobs:
            logger.error("pending jobs(%d) exceeds max threshold(%d)" % (
                self.pending_jobs, self.max_jobs))
            # force a restart since this is critical error
            ept_utils.restart_fabric(self.fabric, 
                "worker job count exceeds max threshold %s" % self.max_jobs)
            return False
        if job.keystr not in self.jobs:
            self.jobs[job.keystr]={"count":0,"fail":0,"wid":self.next_worker}
        wid = self.jobs[job.keystr]["wid"]
        if self.jobs[job.keystr]["count"] > self.max_key_count:
            logger.warn("key count(%d) exceeds max threshold(%d) for w(%s):%s"%(
                self.jobs[job.keystr]["count"], self.max_key_count,
                self.jobs[job.keystr]["wid"], job.keystr))
            self.jobs[job.keystr]["fail"]+=1
            if self.jobs[job.keystr]["fail"]>=self.enqueue_fail_threshold:
                logger.debug("count(%s>%s), moving to rapid queue" % (
                    self.jobs[job.keystr]["fail"],
                    self.enqueue_fail_threshold))
                rjob = EPJob("ep_notify_fail", job.key, ts=job.ts)
                logger.debug("enqueue on worker(%s) job:%s [prQ:%s][rxQ:%s]"%(
                    wid, rjob, self.workers[wid]["prQ"].qsize(), 
                    self.workers[wid]["rxQ"].qsize()))
                self.workers[wid]["prQ"].put(rjob)
                logger.debug("removing key %s from jobs" % job.keystr)
                self.jobs.pop(job.keystr,None)
            return False

        # ok to enqueue the job on worker
        logger.debug("enqueue on worker(%s) job:%s [txQ:%s][rxQ:%s]" % (
            wid, job, self.workers[wid]["txQ"].qsize(), 
            self.workers[wid]["rxQ"].qsize()))
        self.workers[wid]["txQ"].put(job)
        self.jobs[job.keystr]["count"]+=1
        return True

    def handle_name_event(self, e):
        self.enqueue_priority_job(EPJob("handle_event", {}, data={
            "classname": "namedEvent", "event": e}))

    def handle_subnet_event(self, e):
        self.enqueue_priority_job(EPJob("handle_event", {}, data={
            "classname": "subnetEvent", "event": e}))

    def handle_fabricNode(self, e):
        self.enqueue_priority_job(EPJob("handle_event", {}, data={
            "classname":"fabricNode", "event":e}))

    def handle_vpcRsVpcConf(self, e):
        self.enqueue_priority_job(EPJob("handle_event", {}, data={
            "classname":"vpcRsVpcConf", "event":e}))
        
    def handle_fabricExplicitGEp(self, e):
        self.enqueue_priority_job(EPJob("handle_event", {}, data={
            "classname":"fabricExplicitGEp", "event":e}))

    def handle_fabricProtPol(self, e):
        self.enqueue_priority_job(EPJob("handle_event", {}, data={
            "classname":"fabricProtPol", "event":e}))

    def handle_epmMacEp(self, e):
        return self.handle_event("epmMacEp", e) 
    
    def handle_epmIpEp(self, e):
        return self.handle_event("epmIpEp", e) 
        
    def handle_epmRsMacEpToIpEpAtt(self, e):
        return self.handle_event("epmRsMacEpToIpEpAtt", e) 

    def handle_event(self, classname, event):
        """ extract VNID/addr from event and put unique key onto queue """
        #logger.debug("event %s: %s"%(classname,ept_utils.pretty_print(event)))
        key = ept_utils.parse_epm_event(classname, event, self.overlay_vnid)
        if key is not None:
            jkey = {
                "type": key["type"],
                "addr": key["addr"],
                "vnid": key["vnid"]
            }
            # for epmRsMacEpToIpEpAtt, remap addr from mac to ip attribute
            if classname == "epmRsMacEpToIpEpAtt": jkey["addr"] = key["ip"]
            job = EPJob("ep_analyze", jkey, ts=key["ts"], data=key)
            if not self.enqueue_job(job):
                logger.debug("failed to enqueue job:%s" % job.keystr)
        else:
            logger.warn("failed to parse key from event")

def start_ep_worker(**kwargs):
    """ create new ep_worker class and start it. Assumes this is in unique
        processing space
        required kwargs:
            txQ             - transmit queue for sending messages to parent
            rxQ             - receive queue for receiving messages from parent
            prQ             - receive priority queue for critical messages
            fabric          - fabric name
            overlay_vnid    - vnid value for overlay-1
            wid             - worker id
    """
    watcher = kwargs.get("watcher", False)
    for attr in ["wid", "fabric", "overlay_vnid", "txQ", "rxQ", "prQ"]:
        if attr not in kwargs:
            logger.error("missing required attribute: %s" % attr)
            return
    ep_worker = EPWorker(
        kwargs.get("txQ"), kwargs.get("rxQ"), kwargs.get("prQ"), 
        kwargs.get("fabric"), kwargs.get("overlay_vnid"), kwargs.get("wid")
    )
    ep_worker.start()

def start_ep_priority_worker(**kwargs):
    """ start priority worker. Assumes this is in unique processing space
        required kwargs:
            txQ         - transmit queue for sending messages to parent
            rxQ         - receive queue for receiving messages from parent
            prQ         - receive priority queue for critical messages
            bcastQ      - list of other worker rxQ to send bcast message
            bcastPrQ    - list of other worker prQ to send bcast message
            fabric      - fabric name
            wid         - worker id
    """
    for attr in ["txQ", "rxQ", "prQ", "bcastQ", "bcastPrQ", "fabric", "wid"]:
        if attr not in kwargs:
            logger.error("missing required attribute: %s" % attr)
            return
    ep_p_worker = EPPriorityWorker(
        kwargs.get("txQ"), kwargs.get("rxQ"), kwargs.get("prQ"), 
        kwargs.get("bcastQ"), kwargs.get("bcastPrQ"), kwargs.get("fabric"), 
        kwargs.get("wid")
    )
    ep_p_worker.start()


def stage_ep_history_db(fabric, session, app, overlay_vnid):
    """ Instead of directly (re)building ep_history database, this function
        will perform the following:
            - get full list of all required epm objects
            - for eps not currently in the database, create delete job
            - for all other eps, create ep_analyze job and return list
        returns None on error 
    """

    ep_jobs = []    # list of EP_Jobs that will be returned on success
    eps = {}        # current eps in fabric indexed by [node][vnid][addr]

    # pull all endpoints from epmDb restricted to classes we care about
    start_time = time.time()
    js = ept_utils.get_class(session, "epmDb", queryTarget="subtree", 
        targetSubtreeClass="epmMacEp,epmIpEp,epmRsMacEpToIpEpAtt")
    if js is None:
        logger.error("failed to pull inital epmDb from apic")
        return None

    # create an ep_analyze job for each current endpoint and add to eps
    ts = time.time()
    for ep in js:
        if type(ep) is dict and len(ep)==1:
            classname = ep.keys()[0]
            p = ept_utils.parse_epm_event(classname, ep, overlay_vnid, ts=ts)
            if p is None: 
                logger.warn("failed to parse %s: %s" % (classname, ep))
                continue
            jkey = {"type":p["type"],"addr":p["addr"],"vnid":p["vnid"]}
            # for epmRsMacEpToIpEpAtt, remap addr from mac to ip attribute
            if classname == "epmRsMacEpToIpEpAtt": jkey["addr"] = p["ip"]
            ep_jobs.append(EPJob("ep_analyze", jkey, ts=p["ts"], data=p))
            if p["node"] not in eps: eps[p["node"]] = {}
            if p["vnid"] not in eps[p["node"]]: eps[p["node"]][p["vnid"]] = {}
            eps[p["node"]][p["vnid"]][p["addr"]] = 1

    # free memory for js before adding delete jobs
    js = {}

    with app.app_context():
        db = app.mongo.db
        # get all non-delete entries from database and if not currently in eps 
        # append delete event to ep_jobs list
        db_key = {"fabric": fabric,"events.0.status": { "$ne": "deleted"}}
        for h in db.ep_history.find(db_key,{"events":{"$slice":1}}):
            try:
                if h["node"] in eps and h["vnid"] in eps[h["node"]] and \
                    h["addr"] in eps[h["node"]][h["vnid"]]:
                    # entry found in eps so not deleted from fabric
                    continue
                delete_jobs=ep_get_delete_jobs(h,overlay_vnid,event_ts=ts)
                if delete_jobs is None:
                    logger.warn("failed to get delete_jobs for %s" % h)
                else: ep_jobs+= delete_jobs 
            except KeyError as e:
                logger.warn("skipping on %s as key %s is missing"%(h,e))
                continue

    # return list of ep_jobs to replay through subscription thread
    logger.debug("(build)stage_ep_history_db time:%f, jobs:%s" % (
        time.time()-start_time, len(ep_jobs)))
    return ep_jobs
        
def check_apic_health(session):
    # check health of session subscriber thread and websocket is connected
    # perform query to see if session is still alive
    alive = False
    try:
        alive = (
            hasattr(session.subscription_thread, "is_alive") and \
            session.subscription_thread.is_alive() and \
            hasattr(session.subscription_thread, "_ws") and \
            session.subscription_thread._ws.connected and \
            ept_utils.get_dn(session, "uni") is not None
        )
    except Exception as e: pass
    logger.debug("manual check to ensure session is still alive: %r" % alive)
    return alive

def apic_version_trust_subscription(version):
    # after CSCvb36365 (in 2.2(1a) above), we can trust subscription events
    # this function checks provided apic_version to ensure it is greater than
    # or equal to provided fix.  Return boolean or None on error
    # code can be in form d.d(dw) or d.d(d.d) or d.d(d.dw)

    logger.debug("check version trust subscription for: %s" % version)
    if version is None: return None
    version = version.strip()

    # build regex and extract major/minor/build/patch
    reg = "^(?P<major>[0-9]+)\.(?P<minor>[0-9]+)"
    reg+= "\((?P<build>[0-9]+)\.?(?P<patch>[0-9]*[a-z]*)?\)$"
    r1 = re.search(reg, version)
    if r1 is None:
        logger.warn("unable to parse version: %s" % version)
        return None
    major = int(r1.group("major"))
    minor = int(r1.group("minor"))
    build = int(r1.group("build"))
    patch = r1.group("patch")
    logger.debug("version:%s, major:%s, minor:%s, build:%s, patch:%s" % (
        version, major, minor, build, patch))
    if major < 2: trust = False
    elif major == 2:
        if minor < 2 : trust = False
        elif minor == 2: 
            if build >= 1 : trust = True
            else: trust = False
        else: trust = True
    else: trust = True
    logger.debug("version %s trust_subscription: %r" % (version, trust))
    return trust
