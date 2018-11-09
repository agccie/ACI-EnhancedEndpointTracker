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

    def __init__(self, fabric, interests, **kwargs):
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
            name (str)          subscription_ctrl name useful for debugs with multiple subscriptions
                                within the same process/thread
            only_new (bool)     do not return existing objects, only newly received events
            heartbeat (int)     dead interval to check health of session
            inactive_interval(float) interval in seconds to sleep between loop when no events have 
                                been detected and no callbacks are ready
            subscribe_timeout(int) maximum amount of time to wait for non-blocking subscription to 
                                start. If exceeded the subscription is aborted
        """

        self.fabric = fabric
        self.interests = interests
        self.only_new  = kwargs.get("only_new", True)
        self.heartbeat = kwargs.get("heartbeat", 60.0)
        self.inactive_interval = kwargs.get("inactive_interval", 0.5)
        self.subscribe_timeout = kwargs.get("subscribe_timeout", 10.0)
        self.name = kwargs.get("name", "")

        # state of the session
        self.worker_thread = None
        self.last_heartbeat = 0
        self.session = None
        self.alive = False
        self.paused = False
        self.queued_events = []
        self.lock = threading.Lock()
        self.ctrl = SubscriptionCtrl.CTRL_CONTINUE

    def is_alive(self):
        """ determine if subscription is still alive """
        return self.alive

    def pause(self):
        """ pause subscription callback.  This is useful to keep the subscription alive and queue
            the susbscriptions events until caller is ready to handle callbacks
        """
        logger.info("%s pausing subscription", self.name)
        self.paused = True

    def resume(self):
        """ if the subscription has been paused, executing resume to 'unpause' and trigger handler
            of all pending events that have been received while subscription was paused. Note, it
            can take upt to the inactive_interval before the queued events are triggered
        """
        logger.info("%s resuming subscription", self.name)
        self.paused = False

    def restart(self, blocking=True):
        """ restart subscription
       
            blocking (bool)     by default subscriptions block while the 
                                subscription is active. If blocking is set to
                                false then subscription is handled in background     
        """
        logger.info("%s restart: (alive: %r, thread: %r)", self.name, self.alive,
                    (self.worker_thread is not None))
        # unconditionally flush queued_events on unsubscribe or restart
        self.queued_events = []
        # if called from within worker then just update self.ctrl
        if self.worker_thread is threading.current_thread():
            # unconditionally flush queued_events on _close or restart
            self.queued_events = []
            with self.lock:
                self.ctrl = SubscriptionCtrl.CTRL_RESTART
        else:
            # if subscription is already active, wait for it close
            self.unsubscribe()
            self.subscribe(blocking=blocking)
  
    def unsubscribe(self):
        """ unsubscribe and close connections """
        logger.info("%s unsubscribe: (alive:%r, thread:%r)", self.name, self.alive,
                    (self.worker_thread is not None))
        if not self.alive: return

        # should never call unsubscribe without worker (subscribe called with block=True), however 
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
 
    def subscribe(self, blocking=True):
        """ start subscription and handle appropriate callbacks 

            blocking (bool)     by default subscriptions block while the 
                                subscription is active. If blocking is set to
                                false then subscription is handled in background

            Note, when blocking=False, the main thread will still wait until
            subscription has successfully started (or failed) before returning
        """
        logger.info("%s start subscribe (blocking:%r)", self.name, blocking)

        # get lock to set ctrl
        logger.debug("setting ctrl to close")
        with self.lock:
            self.ctrl = SubscriptionCtrl.CTRL_CONTINUE

        # never try to subscribe without first killing previous sessions
        self.unsubscribe()
        if blocking: 
            self._subscribe_wrapper()
        else:
            self.worker_thread = threading.Thread(target=self._subscribe_wrapper)
            self.worker_thread.daemon = True
            self.worker_thread.start()
            
            # wait until subscription is alive or exceeds timeout
            ts = time.time()
            while not self.alive:
                if time.time() - ts  > self.subscribe_timeout:
                    logger.debug("failed to start subscription")
                    self.unsubscribe()
                    return
                logger.debug("waiting for subscription to start")
                time.sleep(1) 
        logger.debug("subscription successfully started")

    def _subscribe_wrapper(self):
        """ handle _subscribe with wrapper for ctrl restart signals """
        restarting = False
        while self.ctrl == SubscriptionCtrl.CTRL_CONTINUE:
            self._subscribe(restarting=restarting)
            if self.ctrl == SubscriptionCtrl.CTRL_RESTART:
                logger.debug("restart request, resting subscription ctrl to continue")
                with self.lock:
                    self.ctrl = SubscriptionCtrl.CTRL_CONTINUE
                    restarting = True

    def _subscribe(self, restarting=False):
        """ handle subscription within thread """
        logger.debug("subscription thread starting")

        # initialize subscription is not alive unless in restarting status
        self.alive = restarting

        # dummy function that does nothing
        def noop(*args,**kwargs): pass

        # verify caller arguments
        if type(self.interests) is not dict or len(self.interests)==0:
            logger.error("invalid interests for subscription: %s", interest)
            self.alive = False
            return

        for cname in self.interests:
            if type(self.interests[cname]) is not dict or "handler" not in self.interests[cname]:
                logger.error("invalid interest %s: %s", cname, self.interest[cname])
                self.alive = False
                return
            if not callable(self.interests[cname]["handler"]):
                logger.error("handler '%s' for %s is not callable", self.interests[cname]["handler"], 
                        cname)
                self.alive = False
                return
    
        try: self.heartbeat = float(self.heartbeat)
        except ValueError as e:
            logger.warn("invalid heartbeat '%s' setting to 60.0", self.heartbeat)
            self.heartbeat = 60.0

        # create session to fabric
        self.session = get_apic_session(self.fabric, subscription_enabled=True)
        if self.session is None:
            logger.error("subscription failed to connect to fabric")
            self.alive = False
            return

        for cname in self.interests:
            # assume user knows what they are doing here - if only_new is True then return set is
            # limited to first 10.  Else, page-size is set to maximum
            if self.only_new:
                url = "/api/class/%s.json?subscription=yes&page-size=10" % cname
            else:
                url = "/api/class/%s.json?subscription=yes&page-size=75000" % cname
            self.interests[cname]["url"] = url
            resp = self.session.subscribe(url, only_new=self.only_new)
            if resp is None or not resp.ok:
                logger.warn("failed to subscribe to %s",  cname)
                self.alive = False
                return
            logger.debug("successfully subscribed to %s", cname)

        # successfully subscribed to all objects
        self.alive = True

        def continue_subscription():
            # return true if ok to continue monitoring subscription, else cleanup and return false
            if self.ctrl != SubscriptionCtrl.CTRL_CONTINUE:
                logger.debug("exiting subscription due to ctrl: %s",self.ctrl)
                self._close_subscription()
                return False
            return True

        # listen for events and send to handler
        self.last_heartbeat = time.time()
        while True:
            # check ctrl flags and exit if set to quit
            if not continue_subscription(): return

            # flush queued events if no longer paused
            if not self.paused and len(self.queued_events) > 0:
                logger.debug("unpaused, triggering callback of %s events", len(self.queued_events))
                for (func, event) in self.queued_events:
                    func(event)
                    if not continue_subscription(): return
                self.queued_events = []

            interest_found = False
            ts = time.time()
            for cname in self.interests:
                url = self.interests[cname]["url"]
                count = self.session.get_event_count(url)
                if count > 0:
                    #logger.debug("1/%s events found for %s", count, cname)
                    if self.paused:
                        self.queued_events.append((
                            self.interests[cname]["handler"], 
                            self.session.get_event(url)
                        ))
                        logger.debug("%s paused, event %s queued", cname, len(self.queued_events))
                    else:
                        self.interests[cname]["handler"](self.session.get_event(url))
                    interest_found = True
                    # if event forced subscription closed, don't pick up next event
                    if not continue_subscription(): return

            # update last_heartbeat or if exceed heartbeat, check session health
            if interest_found: 
                self.last_heartbeat = ts
            elif (ts-self.last_heartbeat) > self.heartbeat:
                logger.debug("checking session status, last_heartbeat: %s",
                    self.last_heartbeat)
                if not self.check_session_subscription_health():
                    logger.warn("session no longer alive")
                    self._close_subscription()
                    return
                self.last_heartbeat = ts
            else: time.sleep(self.inactive_interval)

    def _close_subscription(self):
        """ try to close any open subscriptions """
        logger.debug("close all subscriptions")
        self.alive = False
        # unconditionally flush queued_events on unsubscribe
        self.queued_events = []
        if self.session is not None:
            try:
                urls = self.session.subscription_thread._subscriptions.keys()
                for url in urls:
                    if "?" in url: url = "%s&page-size=1" % url
                    else: url = "%s?page-size=1" % url
                    logger.debug("close subscription url: %s", url)
                    self.session.unsubscribe(url)
                self.session.close()
            except Exception as e:
                logger.warn("failed to close subscriptions: %s", e)
                logger.debug(traceback.format_exc())

    def check_session_subscription_health(self):
        """ check health of session subscription thread and that corresponding
            websocket is still connected.  Additionally, perform query on uni to 
            ensure connectivity to apic is still present
            return True if all checks pass else return False
        """
        alive = False
        try:
            alive = (
                hasattr(self.session.subscription_thread, "is_alive") and \
                self.session.subscription_thread.is_alive() and \
                hasattr(self.session.subscription_thread, "_ws") and \
                self.session.subscription_thread._ws.connected and \
                get_dn(self.session, "uni", timeout=10) is not None
            )
        except Exception as e: pass
        logger.debug("manual check to ensure session is still alive: %r",alive)
        return alive

if __name__ == "__main__":
    
    from ..utils import (pretty_print, setup_logger)
    def handle(event): 
        logger.debug("event: %s", pretty_print(event))

    setup_logger(logger, stdout=True, quiet=True, thread=True)
    logger.debug("let's start this...")

    fabric = "fab3"
    interests = {
        "fvTenant": {"handler": handle},
        "fvBD": {"handler": handle},
        "eqptLC": {"handler": handle},
    }
    sub = SubscriptionCtrl(fabric, interests)
    sub.heartbeat = 10
    try:
        sub.subscribe(blocking=True)
    except KeyboardInterrupt as e:
        logger.debug("interrupting main thread!")
    finally:
        sub.unsubscribe()
