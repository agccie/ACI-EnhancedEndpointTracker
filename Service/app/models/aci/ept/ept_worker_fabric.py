import logging
import time

from .common import push_event
from .ept_cache import eptCache
from .ept_msg import eptEpmEventParser
from .ept_settings import eptSettings
from ..utils import email
from ..utils import syslog
from ...utils import get_app_config
from ...utils import get_db

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
        self.db = get_db()
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

    def get_uptime_delta_offset(self, delta=None):
        """ return difference between provided delta and current uptime. If the uptime_delta is 
            less than zero, return 0.  If no delta is provided, then return the uptime.
        """
        uptime = time.time() - self.start_ts
        if delta is None:
            return uptime
        uptime_delta = delta - uptime
        if uptime_delta > 0:
            return uptime_delta
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
        #   overlay if vnid is overlay vnid
        #   external if vnid is in eptVnid table with external set to true
        #   else returns 'epg' (default learn type)
        if "loopback" in flags:
            return "loopback"
        elif "psvi" in flags:
            return "psvi"
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

    def send_notification(self, notify_type, subject, txt):
        # send proper notifications for this fabric.  set notify_type to none to skip enable check
        # and force notification
        notify = self.notification_enabled(notify_type)
        if notify["enabled"]:
            if notify["email_address"] is not None:
                email(
                    msg=txt,
                    subject=subject,
                    sender=get_app_config().get("EMAIL_SENDER", None),
                    receiver=notify["email_address"],
                )
            if notify["syslog_server"] is not None:
                syslog(txt, server=notify["syslog_server"], server_port=notify["syslog_port"])
        else:
            logger.debug("skipping send notification as '%s' is not enabled", notify_type)
