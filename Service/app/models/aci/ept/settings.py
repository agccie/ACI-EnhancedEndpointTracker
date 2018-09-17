
from ...rest import Rest
from ...rest import api_register
from ...rest import api_callback
from ..fabric import Fabric
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
    """ ept settings per fabric auto created with defaults when fabric is created """

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
            "description": "send email notifications on endpoint move",
            "default": False,
        },
        "notify_stale_email":{
            "type": bool,
            "description": "send email notifications on stale endpoint detection",
            "default": False,
        },
        "notify_offsubnet_email":{
            "type": bool, 
            "description": "send email notifications on off-subnet endpoint detection",
            "default": False,
        },
        "notify_move_syslog": {
            "type": bool, 
            "description": "send syslog notifications on endpoint move",
            "default": False,
        },
        "notify_stale_syslog": {
            "type": bool, 
            "description": "send syslog notifications on stale endpoint detection",
            "default": False,
        },
        "notify_offsubnet_syslog": {
            "type": bool, 
            "description": "send syslog notifications on off-subnet endpoint detection",
            "default": False,
        },
        "auto_clear_stale": {
            "type": bool,
            "description": "auto-clear endpoints detected as stale on the affected node",
            "deafult": False,
        },
        "auto_clear_offsubnet": {
            "type": bool,
            "description": "auto-clear endpoints detected as off-subnet on the affected node",
            "default": False,
        },
        "analyze_move": {
            "type": bool,
            "description": "perform move analysis on each endpoint event",
            "default": True,
        },
        "analyze_stale": {
            "type": bool,
            "description": "perform stale analysis on each endpoint event (ip endpoints only)",
            "default": True,
        },
        "analyze_offsubnet": {
            "type": bool,
            "description": "perform offsubnet analysis on each endpoint event (ip endpoints only)",
            "default": True,
        },
        "max_ep_events":{
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
        "max_workers":{
            "type": int,
            "description": " maximum number of worker processes",
            "default": 6,
            "min_val": 1, 
            "max_val": 128,
        },
        "max_jobs":{
            "type": int,
            "description": """
            maximum queue size of pending events to process during steady-state. When this number is
            exceeded the fabric monitor is restarted.
            """,
            "default": 65536,
            "min_val": 1024, 
            "max_val": 1048576,
        },
        "max_startup_jobs":{
            "type": int,
            "description": """
            maximum queue size of endpoints events to process during fabric startup. This number 
            must be high enough to support the total number of EPM objects within the fabric.
            """,
            "default": 256000,
            "min_val": 1024, 
            "max_val": 1048576,
        },
        "overlay_vnid": {
            "type": int,
            "write": False,
            "description": "dynamically discovered overlay vnid"
        },
    }

