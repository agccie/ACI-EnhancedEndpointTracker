
from ... utils import get_app_config
from ... utils import get_db
from .. utils import get_apic_session
from .. utils import send_emails
from .. utils import syslog
from . common import NOTIFY_INTERVAL
from . common import NOTIFY_QUEUE_MAX_SIZE
from . common import BackgroundThread
from . common import push_event
from . ept_cache import eptCache
from . dns_cache import DNSCache
from . ept_msg import eptEpmEventParser
from . ept_settings import eptSettings
from six.moves.queue import Queue
from six.moves.queue import Full

import logging
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class eptWorkerFabric(object):
    """ tracks cache and settings for each fabric actively being monitored, also provides useful
        notification and push_event functions
    """
    def __init__(self, fabric):
        self.fabric = fabric
        self.start_ts = time.time()
        self.settings = eptSettings.load(fabric=fabric, settings="default")
        self.cache = eptCache(fabric)
        self.dns_cache = DNSCache()
        self.db = get_db()
        self.watcher_paused = False
        self.session = None
        self.notify_queue = None
        self.notify_thread = None
        self.init() 

    def init(self):
        """ initialize settings after fabric settings as been loaded """
        # epm parser used with eptWorker for creating pseudo eevents
        self.ept_epm_parser = eptEpmEventParser(self.fabric, self.settings.overlay_vnid)
        # one time calculation for email address and syslog server (which requires valid port)
        self.email_address = self.settings.email_address
        self.syslog_server = self.settings.syslog_server
        self.syslog_port = self.settings.syslog_port
        if len(self.email_address) == 0: 
            self.email_address = None
        if len(self.syslog_server) == 0:
            self.syslog_server = None
            self.syslog_port = None

    def close(self):
        """ stateful close when worker receives FABRIC_STOP for this fabric """
        if self.db is not None:
            self.db.client.close()
        if self.session is not None:
            self.session.close()
        if self.notify_thread is not None:
            self.notify_thread.exit()
        # remove all objects from notify queue
        if self.notify_queue is not None:
            try:
                logger.debug("clearing notify queue (size: %d)", self.notify_queue.qsize())
                while not self.notify_queue.empty():
                    self.notify_queue.get()
            except Exception as e:
                logger.debug("Traceback:\n%s", traceback.format_exc())
                logger.error("failed to execute clear notify queue %s", e)

    def watcher_init(self):
        """ watcher process needs session object for mo sync and notify queue"""
        logger.debug("wf worker init for %s", self.fabric)
        self.notify_queue = Queue(maxsize=NOTIFY_QUEUE_MAX_SIZE)
        logger.debug("starting worker fabric apic session")
        self.session = get_apic_session(self.fabric)
        if self.session is None:
            logger.error("failed to get session object within worker fabric")

        # watcher will also send notifications within a background thread to ensure that 
        # any delay in syslog or email does not backup other service events
        self.notify_thread = BackgroundThread(func=self.execute_notify, name="notify", count=0, 
                                            interval=NOTIFY_INTERVAL)
        self.notify_thread.daemon = True
        self.notify_thread.start()

    def settings_reload(self):
        """ reload settings from db """
        logger.debug("reloading settings for %s", self.fabric)
        self.settings.reload()
        self.init()

    def get_uptime_delta_offset(self, delta=None):
        """ return difference between provided delta and current uptime. If the uptime_delta is 
            less than zero, return 0.  If no delta is provided, then return the uptime.
        """
        uptime = time.time() - self.start_ts
        if delta is None: return uptime
        uptime_delta = delta - uptime
        if uptime_delta > 0: return uptime_delta
        return 0

    def push_event(self, table, key, event, per_node=True):
        # wrapper to push an event to eptHistory events list.  set per_node to false to use 
        # max_endpoint_event rotate length, else max_per_node_endpoint_events value is used
        if per_node:
            return push_event(self.db[table], key, event, 
                    rotate=self.settings.max_per_node_endpoint_events)
        else:
            return push_event(self.db[table], key, event, rotate=self.settings.max_endpoint_events)

    def get_learn_type(self, vnid, flags=[]):
        # based on provide vnid and flags return learn type for endpoint:
        #   loopback - if loopback in flags
        #   psvi - if psvi in flags
        #   svi - represents an external SVI (should be set on all external svis)
        #   overlay if vnid is overlay vnid
        #   external if vnid is in eptVnid table with external set to true
        #   else returns 'epg' (default learn type)
        if "loopback" in flags: 
            return "loopback"
        elif "psvi" in flags:
            return "psvi"
        elif "svi" in flags:
            return "external"
        elif vnid == self.settings.overlay_vnid:
            return "overlay"
        ept_vnid = self.cache.get_vnid_name(vnid, return_object=True)
        if ept_vnid is not None and ept_vnid.external:
            return "external"
        return "epg"

    def notification_enabled(self, notify_type):
        # return dict with email address, syslog server, syslog port for notify type. If not enabled,
        # then return None for each field. Set notify_type to 'any_email' or 'any_syslog' to force
        # test of a particular notification type
        ret = {"enabled": False, "email_address": None, "syslog_server": None, "syslog_port": None}
        if notify_type == "move":
            attr = ("notify_move_email", "notify_move_syslog")
        elif notify_type == "stale":
            attr = ("notify_stale_email", "notify_stale_syslog")
        elif notify_type == "offsubnet":
            attr = ("notify_offsubnet_email", "notify_offsubnet_syslog")
        elif notify_type == "clear":
            attr = ("notify_clear_email", "notify_clear_syslog")
        elif notify_type == "rapid": 
            attr = ("notify_rapid_email", "notify_rapid_syslog")
        elif notify_type == "any_email":
            # return all notification types enabled
            ret["enabled"] = True
            ret["email_address"] = self.email_address
            return ret
        elif notify_type == "any_syslog":
            # return all notification types enabled
            ret["enabled"] = True
            ret["syslog_server"] = self.syslog_server
            ret["syslog_port"] = self.syslog_port
            return ret
        else:
            logger.warn("invalid notification type '%s", notify_type)
            return ret
        if getattr(self.settings, attr[0]):
            ret["enabled"] = True
            ret["email_address"] = self.email_address
        if getattr(self.settings, attr[1]):
            ret["enabled"] = True
            ret["syslog_server"] = self.syslog_server
            ret["syslog_port"] = self.syslog_port
        return ret

    def send_notification(self, notify_type, subject=None, txt=None, bulk=None):
        # send proper notifications for this fabric.  set notify_type to none to skip enable check
        # and force notification. user can set bulk to list of (subject/txt) tuples to send a list
        # of notifications at the same time.  All notifications must be of the same notify_type.
        success = True
        errmsg = ""
        notify = self.notification_enabled(notify_type)
        if notify["enabled"]:
            if notify["email_address"] is not None:
                emails = []
                if bulk is not None:
                    for (bulk_subject, bulk_txt) in bulk:
                        emails.append({
                            "sender": get_app_config().get("EMAIL_SENDER", None),
                            "receiver": notify["email_address"],
                            "subject": bulk_subject,
                            "msg": bulk_txt,
                        })
                else:
                    emails.append({
                        "sender": get_app_config().get("EMAIL_SENDER", None),
                        "receiver": notify["email_address"],
                        "subject": subject,
                        "msg": txt,
                    })
                # send_email already supports a list of emails, so simply send all at once
                (success, errmsg) = send_emails(
                    settings = self.settings,
                    dns_cache = self.dns_cache,
                    emails=emails
                )
                if not success:
                    logger.warn("failed to send email: %s", errmsg)
            if notify["syslog_server"] is not None:
                if bulk is not None:
                    for (bulk_subject, bulk_txt) in bulk:
                        syslog(bulk_txt, 
                            dns_cache=self.dns_cache,
                            server=notify["syslog_server"], 
                            server_port=notify["syslog_port"],
                        )
                else:
                    syslog(txt, 
                        dns_cache=self.dns_cache,
                        server=notify["syslog_server"],
                        server_port=notify["syslog_port"],
                    )
            return (success, errmsg)
        else:
            logger.debug("skipping send notification as '%s' is not enabled", notify_type)
            return (False, "notification not enabled")

    def queue_notification(self, notify_type, subject, txt):
        # queue notification that will be sent at next iteration of NOTIFY_INTERVAL
        if self.notify_queue is None:
            logger.error("notify queue not initialized for worker fabric")
            return
        try:
            logger.debug("enqueuing %s notification (queue size %d)", notify_type, 
                self.notify_queue.qsize())
            self.notify_queue.put_nowait((notify_type, subject, txt, time.time()))
        except Full as e:
            logger.error("failed to enqueue notification, queue is full (size: %s)", 
                self.notify_queue.qsize())

    def execute_notify(self):
        # send any notifications sitting in queue, log number of notifications sent and max queue
        # time. We want to support bulk notifications (mainly for email to prevent multiple login
        # on smpt_relay_auth setups) so this function will sort based on notify type and execute
        # send notification with bulk flag.
        msgs = {}  # indexed by notify type and contains tuple (subject,txt)
        count = 0
        max_queue_time = 0
        while not self.notify_queue.empty():
            (notify_type, subject, txt, q_ts) = self.notify_queue.get()
            count+= 1
            q_time = time.time() - q_ts
            if q_time > max_queue_time:
                max_queue_time = q_time
            if notify_type not in msgs:
                msgs[notify_type] = []
            msgs[notify_type].append((subject, txt))
        for notify_type in msgs:
            self.send_notification(notify_type, bulk=msgs[notify_type])
        if count > 0:
            logger.debug("sent %s notifications, max queue time %0.3f sec", count, max_queue_time)


