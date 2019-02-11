
import datetime
import json
import logging
import subprocess
import time

# module level logging
logger = logging.getLogger(__name__)

def pretty_print(js):
    """ try to convert json to pretty-print format """
    try:
        return json.dumps(js, indent=4, separators=(",", ":"), sort_keys=True)
    except Exception as e:
        return "%s" % js

def run_command(cmd, ignore=False, log=None):
    """ use subprocess.check_output to execute command on shell and return output
        if ignore is set to False, then None is returned on execution error
        else stderr is returned on error
        if log file pointer is provided, then both stdout and stderr are writting to log
    """
    logger.debug("run cmd: \"%s\"", cmd)
    try:
        if log is None:
            out = subprocess.check_output(cmd,shell=True,stderr=subprocess.STDOUT)
            return out
        else:
            subprocess.check_output(cmd, shell=True, stderr=log, stdout=log)
            return ""
    except subprocess.CalledProcessError as e:
        logger.debug("error executing command: %s", e)
        logger.debug("stderr:\n%s", e.output)
        if ignore: 
            return e.output

_tz_string = None
def current_tz_string():
    """ returns padded string UTC offset for current server
        +/-xxx
    """
    global _tz_string
    if _tz_string is not None: return _tz_string
    offset = time.timezone if (time.localtime().tm_isdst==0) else time.altzone
    offset = -1*offset
    ohour = abs(int(offset/3600))
    omin = int(((abs(offset))-ohour*3600)%60)
    if offset>0:
        _tz_string = "Z+%s.%s" % ('{0:>02d}'.format(ohour), '{0:>02d}'.format(omin))
    else:
        _tz_string =  "Z-%s.%s" % ('{0:>02d}'.format(ohour), '{0:>02d}'.format(omin))
    return _tz_string

def format_timestamp(timestamp, datefmt="%Y-%m-%dT%H-%M-%S", msec=False):
    """ format timestamp to datetime string """
    try:
        t= datetime.datetime.fromtimestamp(int(timestamp)).strftime(datefmt)
        if msec:
            if timestamp == 0: 
                t = "%s.000" % t
            else: 
                t="{0}.{1:03d}".format(t, int((timestamp*1000)%1000))
        t = "%s%s" % (t, current_tz_string())
        return t
    except Exception as e:
        return timestamp

