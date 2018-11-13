
from ... utils import get_app_config
from ... utils import get_db
from .. utils import email
from .. utils import syslog
from . common import push_event
from . ept_cache import eptCache
from . ept_msg import eptEpmEventParser
from . ept_settings import eptSettings

import logging

# module level logging
logger = logging.getLogger(__name__)

class eptWorkerFabric(object):
    """ tracks cache and settings for each fabric actively being monitored, also provides useful
        notification and push_event functions
    """
    def __init__(self, fabric):
        self.fabric = fabric
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

    def push_event(self, table, key, event, per_node=True):
        # wrapper to push an event to eptHistory events list.  set per_node to false to use 
        # max_endpoint_event rotate length, else max_per_node_endpoint_events value is used
        if per_node:
            return push_event(self.db[table], key, event, 
                    rotate=self.settings.max_per_node_endpoint_events)
        else:
            return push_event(self.db[table], key, event, rotate=self.settings.max_endpoint_events)

    def notification_enabled(self, notify_type):
        # return dict with email address, syslog server, syslog port for notify type. If not enabled,
        # then return None for each field.
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
        # send proper notifications for this fabric 
        notify = self.notification_enabled(notify_type)
        if notify["enabled"]:
            if notify["email_address"] is not None:
                email(
                    msg=txt,
                    subject=subject,
                    sender = get_app_config().get("EMAIL_SENDER", None),
                    receiver=notify["email_address"],
                )
            if notify["syslog_server"] is not None:
                syslog(txt, server=notify["syslog_server"], server_port=notify["syslog_port"])
        else:
            logger.debug("skipping send notification as '%s' is not enabled", notify_type)
