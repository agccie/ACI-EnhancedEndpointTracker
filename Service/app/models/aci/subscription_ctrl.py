"""
    ACI App subscription_ctrl
    @author agossett@cisco.com
"""

from . utils import get_apic_session
from . utils import get_dn

import logging
import threading
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class SubscriptionCtrl(object):
    """ subscription controller """

    CTRL_QUIT       = 1
    CTRL_CONTINUE   = 2
    CTRL_RESTART    = 3

    def __init__(self, fabric, interests={}, only_new=True, subscribe_timeout=10,
            heartbeat_interval=60, heartbeat_max_retries=3, heartbeat_timeout=10):
        """
            fabric (str or instance of Fabric object)

            {
                "classname": {          # classname in which to subscribe
                    "handler": <func>   # callback function for object event
                                        # must accept single event argument
                },
            }  
            each event is dict with following attributes:
                "_ts": float timestamp event was received on server
                "imdata": list of objects within the event

            additional kwargs:
            only_new (bool)     do not return existing objects, only newly received events
            subscribe_timeout(int) maximum amount of time to wait for non-blocking subscription to 
                                start. If exceeded the subscription is aborted. This time is per
                                subscription.  I.e., if there are 30 objects to subscribe to and
                                the timeout is 10 seconds, then script will wait at most 300 secs.
            heartbeat_interval (int)    regular interval to perform heartbeat check. Set to 0 to
                                        disable heartbeat check and rely only on websocket health
            heartbeat_max_retries (int) maximum number of failed heartbeats before apic is marked
                                        as unreachable.
            heartbeat_timeout (int)     timeout for single heartbeat query
        """

        self.fabric = fabric
        self.interests = {}
        self.only_new  = only_new 
        self.subscribe_timeout = subscribe_timeout
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_max_retries = heartbeat_max_retries
        self.heartbeat_timeout = heartbeat_timeout

        # state of the session
        self.worker_thread = None
        self.last_heartbeat = 0
        self.heartbeat_failures = 0
        self.heartbeat_total_success = 0
        self.heartbeat_total_failures = 0
        self.heartbeat_total = 0
        self.session = None
        self.alive = False
        self.failure_reason = None
        self.lock = threading.Lock()
        self.ctrl = SubscriptionCtrl.CTRL_CONTINUE

        # verify interest dict
        if type(interests) is not dict:
            raise Exception("invalid interest, must be type dict" % interests)
        for cname in interests:
            if type(interests[cname]) is not dict or "handler" not in interests[cname]:
                raise Exception("invalid interest %s: %s" % (cname, interests[cname]))
            if not callable(interests[cname]["handler"]):
                raise Exception("handler '%s' for %s is not callable" % (
                    interests[cname]["handler"], cname))
            self.add_interest(cname, interests[cname]["handler"])

    def add_interest(self, classname, callback, paused=False):
        """ add an interest for subscription callback """
        if classname not in self.interests:
            self.interests[classname] = {
                "url": "",
                "paused": paused,
                "handler": callback
            }
            if self.is_alive():
                # subscription already running, we need execute subscribe for new classname
                return self._subscribe_to_interest(classname)
        else:
            logger.debug("ignoring add interest for existing classname: %s", classname)
        return True

    def remove_interest(self, classname):
        """ remove (unsubscribe) from one or more classname """
        if type(classname) is not list:
            classname = [classname]
        for c in classname:
            self._unsubscribe_from_interest(c)

    def set_failure(self, msg):
        """ set a failure reason if no failure reason currently exists.  Note, the first failure
            event is generally the most interesting to be propagated to the user and failure is
            cleared when thread starts running. Here we also want to prefer session failures over
            the provided failure
        """
        if self.failure_reason is None:
            # first check if there are any more specific failures that might have occurred on
            # session threads
            if self.session is not None:
                # prefer subscription_thread, then subscription_thread event_handler_thread, and
                # finally check login_thread
                if self.session.subscription_thread is not None:
                    sub_thread = self.session.subscription_thread
                    if sub_thread.failure_reason is not None:
                        self.failure_reason = sub_thread.failure_reason
                        logger.debug("setting failure reason from subscription thread: %s",
                            self.failure_reason)
                    elif sub_thread.event_handler_thread is not None and \
                        sub_thread.event_handler_thread.failure_reason is not None:
                        self.failure_reason = sub_thread.event_handler_thread.failure_reason
                        logger.debug("setting failure reason from event handler thread: %s",
                            self.failure_reason)
                # check login_thread if no reason found
                if self.failure_reason is None and self.session.login_thread is not None and \
                    self.session.login_thread.failure_reason is not None:
                    self.failure_reason = self.session.login_thread.failure_reason
                    logger.debug("setting failure reason from login thread: %s", self.failure_reason)

            # if nothing else has set failure reason, then use subscription_ctrl reason
            if self.failure_reason is None:
                self.failure_reason = msg
                logger.debug("setting failure reason to subscription_ctrl reason: %s",
                    self.failure_reason)

    def is_alive(self):
        """ determine if subscription is still alive """
        return self.alive

    def pause(self, classname):
        """ pause subscription callback for one or more classnames within interest.  
            This is useful to keep the subscription alive and queue the susbscriptions events until 
            caller is ready to handle callbacks
        """
        if type(classname) is not list:
            classname = [classname]
        logger.debug("pause subscription for %s", classname)
        for c in classname:
            if c in self.interests:
                self.interests[c]["paused"] = True
                if self.session is not None and self.session.subscription_thread is not None:
                    self.session.subscription_thread.pause(self.interests[c]["url"])
            else:
                logger.debug("skipping pause for unknown interest: %s", c)

    def resume(self, classname):
        """ resume (unpause) subscription callback for one or more classnames within interests
            note this triggers callback of all pending events within event queue 
        """
        if type(classname) is not list:
            classname = [classname]
        logger.info("resuming subscription for %s", classname)
        for c in classname:
            if c in self.interests:
                self.interests[c]["paused"] = False
                if self.session is not None and self.session.subscription_thread is not None:
                    self.session.subscription_thread.resume(self.interests[c]["url"])
            else:
                logger.debug("skipping pause for unknown interest: %s", c)

    def restart(self, blocking=True):
        """ restart subscription
       
            blocking (bool)     by default subscriptions block while the 
                                subscription is active. If blocking is set to
                                false then subscription is handled in background     
        """
        logger.info("restart: (alive: %r, thread: %r)",self.alive,(self.worker_thread is not None))
        # if called from within worker then just update self.ctrl
        if self.worker_thread is threading.current_thread():
            with self.lock:
                self.ctrl = SubscriptionCtrl.CTRL_RESTART
        else:
            # if subscription is already active, wait for it close
            self.unsubscribe()
            self.subscribe(blocking=blocking)
  
    def unsubscribe(self):
        """ unsubscribe and close connections """
        logger.info("unsubscribe: (alive:%r, thread:%r)",self.alive,(self.worker_thread is not None))
        if not self.alive: 
            return

        # should never call unsubscribe without worker_thread (subscribe called with block=True)
        # as sanity check let's put it in there...
        if self.worker_thread is None:
            self._close_subscription()
            return

        # get lock to set ctrl
        logger.debug("setting ctrl to close")
        with self.lock:
            self.ctrl = SubscriptionCtrl.CTRL_QUIT
           
        # wait for child thread to die
        logger.debug("waiting for worker thread to exit")
        if self.worker_thread is threading.current_thread():
            logger.debug("worker_thread is current_thread, cannot join")
        else:
            self.worker_thread.join() 
            self.worker_thread = None
            logger.debug("worker thread closed")
 
    def subscribe(self, blocking=True, session=None):
        """ start subscription and handle appropriate callbacks 

            session (opt)       provide a session object for the subscription.  This is useful when
                                if user already has a session object and does not want parallel 
                                sessions running to the same apic.

            blocking (bool)     by default subscriptions block while the 
                                subscription is active. If blocking is set to
                                false then subscription is handled in background

            Note, when blocking=False, the main thread will still wait until
            subscription has successfully started (or failed) before returning bool success
        """
        logger.info("start subscription_ctrl subscribe (blocking:%r)", blocking)

        # get lock to set ctrl
        with self.lock:
            self.ctrl = SubscriptionCtrl.CTRL_CONTINUE

        # never try to subscribe without first killing previous sessions
        self.unsubscribe()

        if session is not None:
            logger.debug("using shared session object")
            # override local session with new session (this requires closing any previous session)
            if self.session is not None:
                self.session.close()
            self.session = session

        if blocking: 
            self._subscribe_wrapper()
        else:
            self.worker_thread = threading.Thread(target=self._subscribe_wrapper)
            self.worker_thread.daemon = True
            self.worker_thread.start()
            
            # wait until subscription is alive or exceeds timeout
            ts = time.time()
            while not self.alive and self.worker_thread.is_alive():
                if time.time() - ts  > (self.subscribe_timeout * len(self.interests)):
                    msg = "failed to start %s subscriptions within timeout: %.3f" % (
                                len(self.interests), len(self.interests)*self.subscribe_timeout
                            )
                    logger.warn(msg)
                    self.set_failure(msg)
                    self.unsubscribe()
                    return False
                #logger.debug("waiting for subscription to start")
                time.sleep(1)
            # if worker_thread is no longer running or not alive, then failed to start one or more
            # subscriptions
            if not self.alive or not self.worker_thread.is_alive():
                msg = "failed to start one or more subscriptions"
                logger.warn(msg)
                self.set_failure(msg)
                return False
            logger.debug("subscription successfully started")
            return True

    def _subscribe_wrapper(self):
        """ handle _subscribe with wrapper for ctrl restart signals """
        try:
            threading.currentThread().name = "subctrl-bg"
            restarting = False
            while self.ctrl == SubscriptionCtrl.CTRL_CONTINUE:
                self._subscribe(restarting=restarting)
                if self.ctrl == SubscriptionCtrl.CTRL_RESTART:
                    logger.debug("restart request, resetting subscription ctrl to continue")
                    with self.lock:
                        self.ctrl = SubscriptionCtrl.CTRL_CONTINUE
                        restarting = True
                else:
                    # if subscription returns without restart request then break loop
                    break
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
            self.unsubscribe()

    def _subscribe(self, restarting=False):
        """ handle subscription within thread """
        logger.debug("subscription thread starting")

        # clear any previously set failure_reason
        self.failure_reason = None

        # initialize subscription is not alive unless in restarting status
        self.alive = restarting

        # dummy function that does nothing if no callback available for subscription
        def noop(*args,**kwargs):
            pass
    
        # create session to fabric if not already set
        if self.session is None:
            self.session = get_apic_session(self.fabric)
            if self.session is None:
                logger.error("subscription failed to connect to fabric")
                self.alive = False
                self.set_failure("failed to connect to apic")
                return
        # manually init subscription thread so we can pause if needed
        self.session.init_subscription_thread()
        for classname in self.interests:
            if not self._subscribe_to_interest(classname):
                self.set_failure("failed to subscribe to %s" % classname)
                return

        # successfully subscribed to all objects
        self.alive = True

        # monitor subscription health
        self.last_heartbeat = time.time()
        self.heartbeat_failures = 0
        heartbeat_enabled = self.heartbeat_interval > 0
        logger.debug("heartbeat [enable: %r, interval: %s, timeout: %s, retries: %s]",
            heartbeat_enabled, self.heartbeat_interval, self.heartbeat_timeout,
            self.heartbeat_max_retries)
        while True:
            # check ctrl flags and exit if set to quit
            if not self._continue_subscription():
                return

            ts = time.time()
            heartbeat = False
            if heartbeat_enabled and (ts-self.last_heartbeat) > self.heartbeat_interval:
                logger.debug("checking session status, last_heartbeat: %.3f (delta: %.3f)",
                    self.last_heartbeat, (ts-self.last_heartbeat))
                self.last_heartbeat = ts
                heartbeat = True
            if not self.check_session_subscription_health(heartbeat=heartbeat):
                logger.warn("session no longer alive")
                self.set_failure("subscription session no longer alive")
                self._close_subscription()
                return
            # we could sleep for heartbeat interval but then would miss subscription close event
            time.sleep(1)

    def _subscribe_to_interest(self, classname):
        """ execute subscribe for single classname, return bool success"""
        logger.debug("attempting to subscribe to %s", classname)
        if classname in self.interests:
            # assume user knows what they are doing here - if only_new is True then return set is
            # limited to page-size 1.  Else, page-size is set to maximum
            if self.only_new:
                url = "/api/class/%s.json?subscription=yes&page-size=1" % classname
            else:
                url = "/api/class/%s.json?subscription=yes&page-size=75000" % classname
            self.interests[classname]["url"] = url
            paused = self.interests[classname]["paused"]
            callback = self.interests[classname]["handler"]
            if self.session is None or \
                not self.session.subscribe(url, callback, only_new=self.only_new, paused=paused):
                logger.warn("failed to subscribe to %s",  classname)
                self.set_failure("failed to subscribe to %s" % classname)
                self._close_subscription()
                return False
            else:
                logger.debug("successfully subscribed to %s", classname)
                return True
        else:
            logger.warn("ignoring subscribe for unknown interest classname: %s", classname)
            self.set_failure("failed to subscribe unknown interest %s" % classname)
            return False

    def _unsubscribe_from_interest(self, classname):
        """ execute unsubscribe for single classname """
        if classname in self.interests:
            if self.session is not None:
                self.session.unsubscribe(self.interests[classname]["url"])
            self.interests.pop(classname, None)
        else:
            logger.debug("ignoring unsubscribe for unknown interest: %s", classname)

    def _continue_subscription(self):
        # return true if ok to continue monitoring subscription, else cleanup and return false
        if self.ctrl != SubscriptionCtrl.CTRL_CONTINUE:
            logger.debug("exiting subscription due to ctrl: %s", self.ctrl)
            self._close_subscription()
            return False
        return True

    def _close_subscription(self):
        """ try to close any open subscriptions """
        logger.debug("close all subscriptions")
        self.alive = False
        if self.session is not None:
            try:
                self.session.close()
            except Exception as e:
                logger.warn("failed to close subscriptions: %s", e)
                logger.debug(traceback.format_exc())

    def check_session_subscription_health(self, heartbeat=False):
        """ check health of session subscription thread and that corresponding
            websocket is still connected.  Additionally, perform query on uni to 
            ensure connectivity to apic is still present

            set heartbeat to True to punch the url in addition to thread state

            return True if all checks pass else return False
        """
        alive = False
        try:
            alive = (
                hasattr(self.session.subscription_thread, "is_alive") and \
                self.session.subscription_thread.is_alive() and \
                hasattr(self.session.subscription_thread, "_ws")
            )
            if not alive:
                self.set_failure("subscription thread is not running")
            # only check websocket health if subscription thread is not in graceful restart
            if alive and not self.session.subscription_thread.restarting:
                alive = alive and (
                    self.session.subscription_thread._ws.connected and \
                    hasattr(self.session.subscription_thread.event_handler_thread, "is_alive") and \
                    self.session.subscription_thread.event_handler_thread.is_alive()
                )
                if not alive:
                    self.set_failure("websocket is not connected or event handler thread has died")

            if alive and heartbeat:
                self.heartbeat_total+=1
                hb = get_dn(self.session, "uni", timeout=self.heartbeat_timeout) is not None
                if hb:
                    self.heartbeat_failures = 0
                    self.heartbeat_total_success+= 1
                    logger.debug("heartbeat success [pass/fail/total]=[%s/%s/%s]", 
                        self.heartbeat_total_success,
                        self.heartbeat_total_failures,
                        self.heartbeat_total,
                    )
                else:
                    self.heartbeat_failures+= 1
                    self.heartbeat_total_failures+= 1
                    logger.warn("heartbeat failure(%s) [pass/fail/total]=[%s/%s/%s]", 
                        self.heartbeat_failures,
                        self.heartbeat_total_success,
                        self.heartbeat_total_failures,
                        self.heartbeat_total,
                    )
                    if self.heartbeat_failures >= self.heartbeat_max_retries:
                        self.set_failure("apic heartbeat failure")
                        alive = False
        except Exception as e: 
            logger.debug("Traceback:\n%s", traceback.format_exc())
        return alive

