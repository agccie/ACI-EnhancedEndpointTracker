
import sys, os, subprocess, re, getpass, argparse, logging
from app.tasks.ept import utils as ept_utils

from app.tasks.tools.acitoolkit.acisession import Session
from app.models.users import (Users, setup_local)
from app.models.roles import Roles
from app.models.settings import Settings
from app.models.ept import EP_Settings
from app.models.utils import force_attribute_type
from pymongo import IndexModel
from pymongo.errors import DuplicateKeyError

# setup ept_utils logger
logger = logging.getLogger(__name__)
ept_utils.setup_logger(logger, quiet=True)

def get_ip():
    """ return the first non-loopback IPv4 address found
        return None on error.
    """
    logger.debug("getting local ip address")
    cmd = "ip addr | egrep -o \"inet [0-9\.]+\" | egrep -v \"127.0.0.1\" "
    cmd+= "| egrep -o \"[0-9\.]+\""
    try:    
        logger.debug("cmd: %s" % cmd)
        out = subprocess.check_output(cmd,shell=True,stderr=subprocess.STDOUT)
        out = out.strip().split("\n")   # may be multiple IP's
        if len(out)>0: 
            logger.debug("ip address: [%s]" % out[0])
            return out[0]
        else:
            logger.debug("failed to determine ip address")
    except subprocess.CalledProcessError as e:
        logger.warn("error running shell command:\n%s" % e)
        logger.warn("stderr:\n%s" % e.output)
        return None
    return None

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
        js = ept_utils.get_class(session, "infraCont")
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
        return None

def apic_app_init(args):
    """ initialize this app for execution on APIC
        return boolean success
    """
    app_username = args.apic_app_username
    if app_username is None:
        logger.error("app_username not provided, failed to initialize app")
        print "app_username not provided, failed to initialize app"
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

    app = ept_utils.get_app()
    with app.app_context():
        db = app.mongo.db
        # check if fabric currently exists
        f = db.ep_settings.find_one({"fabric":fabric_domain})
        if f is not None:
            # notifiy user that fabric already exists but setup is
            # effectively successful since table exists - this allows us to
            # perform setup on app boot without checking existing of table
            logger.info("fabric(%s) already exists" % f["fabric"])
            return True
        # manually insert into EP_Settings
        try: 
            override = {"fabric":fabric_domain, "apic_hostname":hostname,
                        "apic_cert": cert_key, "apic_username":app_username}
            update = {}
            for a in EP_Settings.META:
                attr = override.get(a, None)
                if attr is not None:
                    # use override value (best effort)
                    try:
                        update[a] = force_attribute_type(a, 
                            EP_Settings.META[a]["type"],
                            attr, control=EP_Settings.META[a])
                    except Exception as e:
                        update[a] = EP_Settings.META[a]["default"]
                else:
                    # use default value
                    update[a] = EP_Settings.META[a]["default"]
            db.ep_settings.insert_one(update)
            return True
        except DuplicateKeyError as e:
            logger.error("duplicateKey EP_Settings, e: %s" % (e))
            return False
        except Exception as e:
            logger.error("an exception occurred: %s" % e)
            return False

    # some unknown error occurred
    return False

def db_exists():
    """ check if database exists by verifying presents of any of the following
        collections:
            users, settings, ep_settings
    """
    logger.debug("checking if db exists")
    app = ept_utils.get_app()
    with app.app_context():
        db = app.mongo.db
        collections = db.collection_names()
        logger.debug("current collections: %s" % collections)
        if len(collections)>0 and (
            "ep_settings" in collections or "users" in collections or \
            "settings" in collections):
            return True
    return False

def db_setup(args):
    """ delete any existing database and setup all tables for new database """

    logger.debug("setting up new database")

    # default fqdn to local IP address if not set
    if args.fqdn is None:
        fqdn = get_ip()
        if fqdn is None: fqdn = ""

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
    
    app = ept_utils.get_app()
    with app.app_context():
        db = app.mongo.db
        # delete all collections from existing database
        db.settings.drop()
        db.users.drop()
        db.rules.drop()
        db.groups.drop()
        db.ep_settings.drop()
        db.ep_nodes.drop()
        db.ep_vpcs.drop()
        db.ep_tunnels.drop()
        db.ep_history.drop()
        db.ep_moves.drop()
        db.ep_stale.drop()
        db.ep_vnids.drop()
        db.ep_epgs.drop()
        db.ep_subnets.drop()
        db.ep_offsubnet.drop()
           
        # setup collection unique indexex
        db.users.create_index("username", unique=True)
        db.rules.create_index("dn", unique=True)
        db.groups.create_index("group", unique=True)

        # enforce compound index on ept tables
        history_indexes = ["vnid","addr"]
        vnid_indexes = ["fabric", "name"]
        subnet_indexes = ["fabric", "vnid"]
        db.ep_settings.create_index("fabric", unique=True)
        db.ep_history.create_indexes([IndexModel(i) for i in history_indexes])
        db.ep_stale.create_indexes([IndexModel(i) for i in history_indexes])
        db.ep_moves.create_indexes([IndexModel(i) for i in history_indexes])
        db.ep_vnid.create_indexes([IndexModel(i) for i in vnid_indexes]) 
        db.ep_epgs.create_indexes([IndexModel(i) for i in vnid_indexes])
        db.ep_subnets.create_indexes([IndexModel(i) for i in subnet_indexes])
        db.ep_offsubnet.create_indexes([IndexModel(i) for i in history_indexes])
        
        # insert default settings
        c = {}
        for attr in Settings.META:
            c[attr] = Settings.META[attr]["default"]
        c["app_name"] = args.app_name
        c["force_https"] = not args.no_https
        c["sso_url"] = args.sso_url
        c["fqdn"] = fqdn
        result = db.settings.insert_one(c)

        # setup local user
        setup_local(app)

        # insert default admin user along with reserved local user
        try:
            db.users.insert_one({
                "username": args.username,
                "password": Users.hash_pass(pwd),
                "role": Roles.FULL_ADMIN,
                "groups": [],
            })
        except DuplicateKeyError as e:
            # race condition possible in ACI_APP_MODE where unauth requests
            # may create default user - workaround is to use different default
            # usernames.  Also, ok to just catch the error and log
            logger.error("DuplicateKey: failed to insert '%s'"%args.username)
            

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no_verify", action="store_true", dest="no_verify",
        help="do not verify that user wants to proceed")
    parser.add_argument("--username", action="store", dest="username",
        help="admin username", default="admin")
    parser.add_argument("--password", action="store", dest="password",
        help="admin password", default=None)
    parser.add_argument("--app_name", action="store", dest="app_name",
        help="application Name", default="EPTracker")
    parser.add_argument("--no_https", action="store_true", 
        dest="no_https", help="disable https default enforcement")
    parser.add_argument("--sso_url", action="store", dest="sso_url",
        help="sso_url", default="")
    parser.add_argument("--conditional", action="store_true",dest="conditional",
        help="only execute setup if database does not currently exists")
    parser.add_argument("--hostname", action="store",
        dest="hostname", help="fabric hostname/ip address")
    parser.add_argument("--fqdn", action="store", dest="fqdn", default=None,
        help="server fully qualified domain name")
    parser.add_argument("--apic_app_init", action="store_true", 
        dest="apic_app_init", help="initialize this app to run on APIC")
    parser.add_argument("--apic_app_username", action="store", 
        dest="apic_app_username",
        help="appuser username and cert_name used by apic_init",
        default=None)
    
    return parser.parse_args()

if __name__ == "__main__":

    # if path is not defined on the system, then imports will fail when running
    # this script directly.  For simplicity, let's update the path
    sys.path.append(os.path.dirname(os.path.realpath(__file__))+"/")
 
    args = get_args()

    # perform apic app initialization if options provided (overrides db_setup)
    if args.apic_app_init: 
        if apic_app_init(args):
            sys.exit(0)
        else:
            logger.error("failed to initialize app")
            sys.exit(1)

    if not args.no_verify and not args.conditional:
        # this fuction is used for initial setup only - ensure user is aware
        # of impact.
        print """
        This script is intended for setup only. If an existing database exists, 
        it will be deleted. This action cannot be undone.
        """
        while 1:
            confirm = raw_input("Are you sure you want to continue [yes/no]? ")
            if confirm.lower() == "no": sys.exit()
            elif confirm.lower() == "yes": break
            else: print "Please type 'yes' or 'no'"

    # conditional implies that we shouldn't do anything if db already exists
    if args.conditional:
        if db_exists():
            logger.debug("stopping conditional executing db_exists=True")
            sys.exit()

    # else do default operation of db_setup
    db_setup(args)

