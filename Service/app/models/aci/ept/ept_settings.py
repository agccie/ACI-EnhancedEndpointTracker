
from ... rest import Rest
from ... rest import api_register
from ... rest import api_route
from ... rest import api_callback
from .. fabric import Fabric
from . common import subscriber_op
from . ept_msg import MSG_TYPE
from flask import abort
from flask import jsonify
import logging

# module level logging
logger = logging.getLogger(__name__)

# add a callback to fabric to create Settings on after_delete
@api_callback("after_create", cls=Fabric)
def after_fabric_create(data):
    s = eptSettings(fabric=data["fabric"])
    if not s.save():
        logger.error("failed to create fabric settings object")

@api_register(parent="fabric", path="ept/settings")
class eptSettings(Rest):
    """ fabric monitor settings which are automatically created/deleted with fabric objects. For 
        now, all ept.settings objects are keyed by fabric name and a settings value of 'default'.
    """

    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": True,
        "delete": False,
    }

    META = {
        "settings": {
            "type": str,
            "key": True,
            "default": "default",
        },
        "email_address": {
            "type":str,             
            "description": "email address for sending email based notifications",
            "regex":"(^$|^[a-zA-Z0-9\-_\.@\+]+$)",
        },
        "syslog_server":{
            "type":str,
            "regex":"(^$|^[a-zA-Z0-9\-_\.\+]+$)",
            "description": "syslog IP or hostname for sending syslog based notifications",
        },
        "syslog_port":{
            "type": int, 
            "description": "syslog port number",
            "default":514,
            "min": 1,
            "max": 65534,
        },
        "notify_move_email":{
            "type": bool, 
            "default": False,
            "description": "send email notifications on endpoint move",
        },
        "notify_stale_email":{
            "type": bool,
            "default": False,
            "description": "send email notifications on stale endpoint detection",
        },
        "notify_offsubnet_email":{
            "type": bool, 
            "default": False,
            "description": "send email notifications on off-subnet endpoint detection",
        },
        "notify_clear_email": {
            "type": bool,
            "default": False,
            "description": "send email notification for clear endpoint events",
        },
        "notify_rapid_email": {
            "type": bool,
            "default": False,
            "description": "send email notification for rapid endpoint events",
        },
        "notify_move_syslog": {
            "type": bool, 
            "default": False,
            "description": "send syslog notifications on endpoint move",
        },
        "notify_stale_syslog": {
            "type": bool, 
            "default": False,
            "description": "send syslog notifications on stale endpoint detection",
        },
        "notify_offsubnet_syslog": {
            "type": bool, 
            "default": False,
            "description": "send syslog notifications on off-subnet endpoint detection",
        },
        "notify_clear_syslog": {
            "type": bool,
            "default": False,
            "description": "send syslog notification for clear endpoint events",
        },
        "notify_rapid_syslog": {
            "type": bool,
            "default": False,
            "description": "send syslog notification for rapid endpoint events",
        },
        "auto_clear_stale": {
            "type": bool,
            "deafult": False,
            "description": "auto-clear endpoints detected as stale on the affected node",
        },
        "auto_clear_offsubnet": {
            "type": bool,
            "default": False,
            "description": "auto-clear endpoints detected as off-subnet on the affected node",
        },
        "analyze_move": {
            "type": bool,
            "default": True,
            "description": "perform move analysis on each endpoint event",
        },
        "analyze_stale": {
            "type": bool,
            "default": True,
            "description": "perform stale analysis on each endpoint event (ip endpoints only)",
        },
        "analyze_offsubnet": {
            "type": bool,
            "default": True,
            "description": "perform offsubnet analysis on each endpoint event (ip endpoints only)",
        },
        "analyze_rapid": {
            "type": bool,
            "default": True,
            "description": "enable rapid endpoint detection and holddown",
        },
        "refresh_rapid": {
            "type": bool,
            "default": True,
            "description": """
            when an endpoint is_rapid flag is cleared, perform api refresh to ensure db is fully 
            synchronized with the endpoint state within the fabric
            """,
        },
        "max_per_node_endpoint_events":{
            "type": int,
            "description": """
            maximum number of historical endpoint events per endpoint per node.  When this number is
            exceeded the older records are discarded. Note, this value is also used to limit the
            number of stale, move, and off-subnet records per endpoint maintained in the database.
            """,
            "default": 64,
            "min_val": 8, 
            "max_val": 1024,
        },
        "max_endpoint_events": {
            "type": int,
            "description": "maximum number of historical endpoint events for eptEndpoint object",
            "default": 64,
            "min": 8,
            "max": 8192,
        },
        "queue_init_events": {
            "type": bool,
            "default": True,
            "description": """ subscriptions are enabled for several MOs during the initial db 
            build.  If events are received on the subscription before initialization has completed
            these events can be queued and serviced after initialization. The number of events 
            queued is dependent on the rate of events and the build time. It may be desirable to 
            ignore the events during init, in which case queue_init_events should be disabled
            """,
        },
        "queue_init_epm_events": {
            "type": bool,
            "default": True,
            "description": """ similar to queue_init_events, epm event subscription is enabled 
            before initial build/rebuild of the endpoint database. The events cannot be serviced 
            until the build has completed. Ideally, queuing the events during the build ensure that
            no endpoint events are lost, however if there is a high amount of events then it may be
            advantageous to disable the queuing of events until they application is ready to 
            process them.  Set queue_init_epm_events to False to ignore events received during 
            initial epm db build.
            """,
        },
        "stale_no_local": {
            "type": bool,
            "default": True,
            "description": """ treat remote(XR) learns without a corresponding local learn (PL/VL)
            within the fabric as a stale endpoint.
            """,
        },
        "stale_multiple_local": {
            "type": bool,
            "default": True,
            "description": """ treat local entries that do not match expected local entry during 
            stale analysis as a stale endpoint.
            """,
        },
        "rapid_threshold": {
            "type": int,
            "default": 2048,
            "min": 512,
            "max": 65536,
            "description": "number of events per minute before endpoint is marked as rapid",
        },
        "rapid_holdtime": {
            "type": int,
            "default": 600,
            "description": "holdtime to ignore new events for endpoint marked as rapid",
        },
        "tz": {
            "type": str,
            "write": False,
            "description": "fabric timezone setting (this is synchronized when fabric is running)",
            "default": "",
        },
        # internal state info
        "overlay_vnid": {
            "type": int,
            "write": False,
            "read": False,
            "description": "dynamically discovered overlay vnid"
        },
        "vpc_pair_type": {
            "type": str,
            "write": False,
            "read": False,
            "default": "explicit",
            "description": "fabricProtPol pairT attribute (consecutive|reciprocal|explicit)",
        },
    }

    @api_route(path="test/email", methods=["POST"], swag_ret=["success"])
    def test_email(self):
        """ send a test email to ensure settings are valid and email notifications are successful
        """
        if len(self.email_address) == 0:
            abort(400, "no email address configured")
        (success, err_str) = subscriber_op(self.fabric, MSG_TYPE.TEST_EMAIL, qnum=0)
        if success:
            return jsonify({"success": True})
        abort(500, err_str)

    @api_route(path="test/syslog", methods=["POST"], swag_ret=["success"])
    def test_syslog(self):
        """ send a test syslog to ensure settings are valid and syslog notifications are successful
        """
        if len(self.syslog_server) == 0:
            abort(400, "no syslog server configured")
        (success, err_str) = subscriber_op(self.fabric, MSG_TYPE.TEST_SYSLOG, qnum=0)
        if success:
            return jsonify({"success": True})
        abort(500, err_str)

    @api_route(path="reload", methods=["POST"], swag_ret=["success"])
    def reload_settings(self):
        """ send msg to background processes to graceful reload settings. This is used after
            settings are updated to apply them without restarting the fabric monitor.
        """
        (success, err_str) = subscriber_op(self.fabric, MSG_TYPE.SETTINGS_RELOAD, qnum=0)
        if success:
            return jsonify({"success": True})
        abort(500, err_str)


