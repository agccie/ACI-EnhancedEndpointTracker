
import json
import logging
import subprocess

# module level logging
logger = logging.getLogger(__name__)

def pretty_print(js):
    """ try to convert json to pretty-print format """
    try:
        return json.dumps(js, indent=4, separators=(",", ":"), sort_keys=True)
    except Exception as e:
        return "%s" % js

def run_command(cmd, ignore=False):
    """ use subprocess.check_output to execute command on shell and return output
        if ignore is set to False, then None is returned on execution error
        else stderr is returned on error
    """
    logger.debug("run cmd: \"%s\"", cmd)
    try:
        out = subprocess.check_output(cmd,shell=True,stderr=subprocess.STDOUT)
        return out
    except subprocess.CalledProcessError as e:
        logger.debug("error executing command: %s", e)
        logger.debug("stderr:\n%s", e.output)
        if ignore: return e.output

