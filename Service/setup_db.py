
import sys, os, subprocess, re, uuid, getpass, argparse, logging, traceback

from app.models.utils import get_app
from app.models.rest import (registered_classes, Role, Universe)
from app.models.user import User
from app.models.settings import Settings
from app.models.utils import (setup_logger, get_db)
from werkzeug.exceptions import (NotFound, BadRequest)
from pymongo import IndexModel
from pymongo.errors import (DuplicateKeyError, ServerSelectionTimeoutError)
from pymongo import (ASCENDING, DESCENDING)

# specific to this application
from app.models.aci import utils as aci_utils
from app.models.aci.tools.acitoolkit.acisession import Session
from app.models.aci.fabric import Fabric

# setup logger
logger = logging.getLogger(__name__)

# global app for config info
app = get_app()

def get_gateway():
    """ return IP address of default gateway used for aci_app
        return None on error.
    """
    logger.debug("getting default gateway")
    cmd = "ip route | egrep -o \"default via [0-9\.]+\" "
    cmd+= "| egrep -o \"[0-9\.]+\""
    try:    
        logger.debug("cmd: %s" % cmd)
        out = subprocess.check_output(cmd,shell=True,stderr=subprocess.STDOUT)
        out = out.strip().split("\n")   # may be multiple default routes
        if len(out)>0: 
            logger.debug("default gateway: [%s]" % out[0])
            return out[0]
        else:
            logger.debug("failed to determine default gateway")
    except subprocess.CalledProcessError as e:
        logger.warn("error running shell command:\n%s" % e)
        logger.warn("stderr:\n%s" % e.output)
        return None
    return None

def apic_app_init(args):
    """ initialize this app for execution on APIC
        return boolean success
    """
    # conditionally initialize db in non-iteractive way which requires
    # local login username/password
    if args.username is None: args.username = "admin"
    if args.password is None: args.password = "cisco"
    if not db_setup(args):
        logger.error("failed to initialize db")
        return False

    app_username = args.apic_app_username
    if app_username is None:
        logger.error("app_username not provided, failed to initialize app")
        return False

    # set hostname to gateway of docker containiner if not provided
    hostname = args.hostname
    if hostname is None: hostname = get_gateway()
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
                cert_name=apic_username, key=apic_cert,
                subscription_enabled=False)
        resp = session.login(timeout=60)
        if resp is None or not resp.ok:
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

def db_exists():
    """ check if database exists by verifying presents of any of the following
        collections:
            users, settings, aci.settings
    """
    logger.debug("checking if db exists")
    collections = get_db().collection_names()
    logger.debug("current collections: %s" % collections)
    if len(collections)>0 and ("user" in collections and "settings" in collections):
        return True
    return False

def db_setup(args):
    """ delete any existing database and setup all tables for new database 
        returns boolean success
    """
    force = args.force
    logger.debug("setting up new database (force:%r)", force)
    
    if not force and db_exists():
        logger.debug("db already exists")
        return True

    # get password from user if not set
    pwd = args.password
    while pwd is None:
        pwd = getpass.getpass( "Enter admin password: ")
        pwd2 = getpass.getpass("Re-enter password   : ")
        if len(pwd)==0: 
            pwd = None
        elif pwd!=pwd2:
            print "Passwords do not match"
            pwd = None
        elif " " in pwd:
            print "No spaces allowed in password"
            pwd = None
   
    db = get_db()
    # get all objects registred to rest API, drop db and create with 
    # proper keys
    for classname in registered_classes:
        c = registered_classes[classname]
        # drop existing collection
        logger.debug("dropping collection %s" % c._classname)
        db[c._classname].drop()
        # create indexes for searching and unique keys ordered based on key order
        # indexes are unique only if expose_id is disabled
        indexes = []
        for a in c._dn_attributes:
            indexes.append((a,ASCENDING))
        if len(indexes)>0:
            logger.debug("creating indexes for %s: %s",c._classname,indexes)
            db[c._classname].create_index(indexes, unique=not c._access["expose_id"])

    # if uni is enabled then required before any other object is created
    uni = Universe.load()
    uni.save()
        
    # insert settings with user provided values 
    lpass = "%s"%uuid.uuid4()
    s = Settings(
        app_name=args.app_name,
        force_https= not args.no_https,
        lpass = lpass
    )
    try: s.save()
    except BadRequest as e:
        logger.error("failed to create settings: %s. Using all defaults"%e)
        s = Settings(lpass=lpass)
        s.save()
    
    # create admin user with provided password and local user
    u = User(username="local", password=lpass, role=Role.FULL_ADMIN)
    if not u.save(): 
        logger.error("failed to create local user")
        return False
    u = User(username=args.username, password=pwd, role=Role.FULL_ADMIN)
    if not u.save():
        logger.error("failed to create username: %s" % args.username)
        return False

    #successful setup
    return True
        

def get_args():
    desc = """
    db setup for %s:%s 
    
    In app mode, user should execute scripts with --apic_app_init which will
    conditionally trigger db_setup.  Else, user can execute without any args
    and will be prompted as needed for any required settings.
 
    """ % (app.config["APP_VENDOR_DOMAIN"], app.config["APP_ID"])
    parser = argparse.ArgumentParser(description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    parser.add_argument("--username", action="store", dest="username",
        help="default username with admin privileges", 
        default=app.config.get("DEFAULT_USERNAME", "admin"))
    parser.add_argument("--password", action="store", dest="password",
        help="password for default user", 
        default=app.config.get("DEFAULT_PASSWORD", None))
    parser.add_argument("--app_name", action="store", dest="app_name",
        help="application Name", default="ExampleApp")
    parser.add_argument("--no_https", action="store_true", 
        dest="no_https", help="disable https default enforcement")
    parser.add_argument("--force", action="store_true", dest="force",
        help="force db setup even if db currently exists")
    parser.add_argument("--hostname", action="store",
        dest="hostname", help="fabric hostname/ip address")
    parser.add_argument("--apic_app_init", action="store_true", 
        dest="apic_app_init", help="initialize this app to run on APIC")
    parser.add_argument("--apic_app_username", action="store", 
        dest="apic_app_username",
        help="appuser username and cert_name used by apic_init",
        default="%s_%s"%(app.config["APP_VENDOR_DOMAIN"],app.config["APP_ID"]))
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
        else:
            if not db_setup(args):
                logger.error("failed to setup datbase")
                sys.exit(1)
    except ServerSelectionTimeoutError as e:
        logger.error("failed to connect to database: %s" % e)
        sys.exit(1)
    except Exception as e:
        logger.error("unexpected error: %s" % e)
        logger.debug("traceback:\n%s" % traceback.format_exc())
        sys.exit(1)

