

from app.models.rest import registered_classes
from app.models.rest import Role
from app.models.rest import Universe
from app.models.rest.db import db_add_shard
from app.models.rest.db import db_init_replica_set
from app.models.rest.db import db_setup
from app.models.utils import get_app
from app.models.utils import get_app_config
from app.models.utils import setup_logger
from pymongo.errors import ServerSelectionTimeoutError

# specific to this application
from app.models.aci import utils as aci_utils
from app.models.aci.session import Session
from app.models.aci.fabric import Fabric

import argparse
import logging
import os
import re
import sys
import traceback

# setup logger
logger = logging.getLogger(__name__)

# need to trigger get_app to build model before looping through dependancies
app = get_app()
# global app for config info
app_config = get_app_config()

def get_gateway():
    """ return IP address of default gateway used for aci_app
        return None on error.
    """
    logger.debug("getting default gateway")
    cmd = "ip route | egrep -o \"default via [0-9\.]+\" "
    cmd+= "| egrep -o \"[0-9\.]+\""
    out = aci_utils.run_command(cmd)
    if out is not None:
        out = out.strip().split("\n")   # may be multiple default routes
        if len(out)>0: 
            logger.debug("default gateway: [%s]" % out[0])
            return out[0]
        else:
            logger.debug("failed to determine default gateway")
    return None

def apic_app_init(args):
    """ initialize this app for execution on APIC
        return boolean success
    """
    # conditionally initialize db in non-iteractive way which requires
    # local login username/password
    if args.username is None: args.username = "admin"
    if args.password is None: args.password = "cisco"
    if not db_setup(
            app_name = args.app_name,
            username = args.username,
            password = args.password,
            sharding = args.sharding,
            force = args.force
            ):
            logger.error("failed to initialize db")
            return False

    app_username = args.apic_app_username
    if app_username is None:
        logger.error("app_username not provided, failed to initialize app")
        return False

    # set hostname to gateway of docker containiner if not provided
    hostname = args.hostname
    if hostname is None: 
        if app_config.get("HOSTED_PLATFORM","") == "APIC":
            hostname = "https://api.service.apic.local"
        else:
            hostname = get_gateway()
    if hostname is None:
        logger.error("failed to determine gateway/hostname for app")
        return False

    # ensure http or https in hostname
    if not re.search("^http", hostname.lower()):
        hostname = "https://%s" % hostname

    # private key for certificate authentication should be present
    # in /home/app/credentials/plugin.key
    cert_key = "/home/app/credentials/plugin.key"

    # determine fabric domain to use as the fabric name
    fabric_domain = app_get_fabric_domain(hostname, app_username, cert_key)
    if fabric_domain is None:
        logger.warn("fabric domain not found, stopping app_init")
        return False

    # load fabric
    f = Fabric.load(fabric=fabric_domain)
    if not f.exists():
        f.apic_hostname = hostname
        f.apic_username = app_username
        f.apic_cert = cert_key
        f.auto_start = True
        if not f.save():
            logger.error("failed to save fabric settings for: %s",fabric_domain)
            return False
        logger.debug("added fabric %s", fabric_domain)
    else:
        logger.debug("fabric %s already exists", fabric_domain)
    return True

def app_get_fabric_domain(hostname, apic_username, apic_cert):
    """ use provided cert credentials and read infraCont class to get 
        default fabric-domain.
        return None on error
    """
    logger.debug("attempting to get fabric domain from %s@%s" % (
        apic_username, hostname))
    try:
        session = Session(hostname, apic_username, appcenter_user=True, 
                cert_name=apic_username, key=apic_cert)
        if not session.login(timeout=60):
            logger.error("failed to login with cert credentials")
            return None
        js = aci_utils.get_class(session, "infraCont")
        if js is None or len(js) is None:
            logger.error("class infraCont returned no result")
            return None
        for i in js:
            if "infraCont" in i and "attributes" in i["infraCont"]:
                attr = i["infraCont"]["attributes"]
                if "fbDmNm" in attr:
                    fd = re.sub(" ","", attr["fbDmNm"])
                    fd = re.sub("[^a-zA-Z0-9\-\.:_]","", fd)
                    logger.debug("fabric domain is: %s (clean: %s)" % (
                        attr["fbDmNm"], fd))
                    return fd
                else:
                    logger.warn("fbDmNm not in attributes: %s" % attr)
        logger.warn("no valid infraCont/fbDmNm found")
        return None
    except Exception as e: 
        logger.debug("failed to get fabric domain: %s" % e)
        logger.debug("traceback:\n%s" % traceback.format_exc())
        return None

def get_args():
    desc = """
    db setup for %s:%s 
    
    In app mode, user should execute scripts with --apic_app_init which will
    conditionally trigger db_setup.  Else, user can execute without any args
    and will be prompted as needed for any required settings.
 
    """ % (app_config["APP_VENDOR_DOMAIN"], app_config["APP_ID"])
    parser = argparse.ArgumentParser(description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    parser.add_argument("--username", action="store", dest="username",
        help="default username with admin privileges", 
        default=app_config.get("DEFAULT_USERNAME", "admin"))
    parser.add_argument("--password", action="store", dest="password",
        help="password for default user", 
        default=app_config.get("DEFAULT_PASSWORD", None))
    parser.add_argument("--sharding", action="store_true", dest="sharding",
        help="enable sharding on the database")
    parser.add_argument("--add_shard", action="store", dest="add_shard",
        help="add shard to database")
    parser.add_argument("--init_rs", action="store", dest="add_rs", 
        help="initialize replica set")
    parser.add_argument("--configsvr", action="store_true", dest="configsvr",
        help="combine with --init_rs to flag replica set as a configsvr")
    parser.add_argument("--app_name", action="store", dest="app_name",
        help="application Name", default="ExampleApp")
    parser.add_argument("--force", action="store_true", dest="force",
        help="force db setup even if db currently exists")
    parser.add_argument("--hostname", action="store",
        dest="hostname", help="fabric hostname/ip address")
    parser.add_argument("--apic_app_init", action="store_true", 
        dest="apic_app_init", help="initialize this app to run on APIC")
    parser.add_argument("--apic_app_username", action="store", 
        dest="apic_app_username",
        help="appuser username and cert_name used by apic_init",
        default="%s_%s"%(app_config["APP_VENDOR_DOMAIN"],app_config["APP_ID"]))
    parser.add_argument("--stdout", action="store_true", 
        help="redirect debugs to stdout")
    
    return parser.parse_args()

if __name__ == "__main__":

    # if path is not defined on the system, then imports will fail when running
    # this script directly.  For simplicity, let's update the path
    sys.path.append(os.path.dirname(os.path.realpath(__file__))+"/")
 
    args = get_args()
    stdout = args.stdout
    setup_logger(logger, quiet=True, stdout=stdout)
    setup_logger(logging.getLogger("app"), quiet=True, stdout=stdout)

    try:
        if args.apic_app_init: 
            if apic_app_init(args):
                sys.exit(0)
            else:
                logger.error("failed to initialize app")
                sys.exit(1)
        elif args.add_rs:
            if not db_init_replica_set(args.add_rs, configsvr=args.configsvr, primary=True):
                logger.error("failed to initialize replica set: %s", args.add_rs)
                sys.exit(1)
        elif args.add_shard:
            if not db_add_shard(args.add_shard):
                logger.error("failed to add shard: %s", args.add_shard)
                sys.exit(1)
        else:
            if not db_setup(
                app_name = args.app_name,
                username = args.username,
                password = args.password,
                sharding = args.sharding,
                force = args.force
                ):
                logger.error("failed to setup datbase")
                sys.exit(1)
    except ServerSelectionTimeoutError as e:
        logger.error("failed to connect to database: %s" % e)
        sys.exit(1)
    except Exception as e:
        logger.error("unexpected error: %s" % e)
        logger.debug("traceback:\n%s" % traceback.format_exc())
        sys.exit(1)

