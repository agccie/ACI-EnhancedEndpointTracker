import os, sys, logging, json
from datetime import timedelta

# these variables are set from app.json if found. Use app.json as single
# source of truth.
app_vars = {
    "APP_VENDOR_DOMAIN":    "Cisco",
    "APP_ID":               "ExampleApp",
    "APP_VERSION":          "1.0",
}

# read in env.sh file if present and set local environ objects (with filter)
# add pkg to local for import of required packages not bundled with image
appfile = "%s/app.json" % os.path.dirname(os.path.realpath(__file__))
if os.path.exists(appfile):
    try:
        with open(appfile, "r") as f:
            js = json.load(f)
            if "vendordomain" in js: 
                app_vars["APP_VENDOR_DOMAIN"] = js["vendordomain"]
            if "appid" in js:
                app_vars["APP_ID"] = js["appid"]
            if "version" in js:
                app_var["APP_VERSION"] = js["version"]
    except Exception as e: pass

# specify mongo uri
#   mongodb://[username:password@]host1[:port1][,host2[:port2],\
#    ...[,hostN[:portN]]][/[database][?options]]
#MONGO_URI = os.environ.get('MONGO_URI',
#    "mongodb://localhost:27017/devdb?connectTimeoutMS=5000&\
#               socketTimeoutMS=20000&serverSelectionTimeoutMS=5000")
MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
MONGO_PORT = int(os.environ.get("MONGO_PORT", 27017))
MONGO_DBNAME = os.environ.get("MONGO_DBNAME","devdb")
MONGO_SERVER_SELECTION_TIMEOUT_MS = 5000
MONGO_CONNECT_TIMEOUT_MS = 5000
MONGO_SOCKET_TIMEOUT_MS = 20000

# enable application debugging (ensure debugging is disabled on production app)
DEBUG = bool(int(os.environ.get("DEBUG", 1)))

# disable pretty print by default to help with large repsonses
JSONIFY_PRETTYPRINT_REGULAR = bool(int(
                            os.environ.get("JSONIFY_PRETTYPRINT_REGULAR",0)))

# authentication settings
REMEMBER_COOKIE_DURATION = timedelta(
    days=int(os.environ.get("REMEMBER_COOKIE_DURATION",1)))
BCRYPT_LOG_ROUNDS = 12
LOGIN_ENABLED = bool(int(os.environ.get("LOGIN_ENABLED",0)))
DEFAULT_USERNAME = os.environ.get("DEFAULT_USERNAME", "admin")
DEFAULT_PASSWORD = os.environ.get("DEFAULT_PASSWORD", "cisco")
PROXY_URL = os.environ.get("PROXY_URL", "http://127.0.0.1:80/")
ENABLE_CORS = bool(int(os.environ.get("ENABLE_CORS",0)))
SECRET_KEY = os.environ.get("SECRET_KEY", "fdcb1c2c9ecbf13d4ae8776f7af13cc5")
EKEY = os.environ.get("EKEY", "4e6d7a92fbbcf2c40c8d629a60b515f1")
EIV  = os.environ.get("EIV", "5bb0f66133e6ac8c96af39bcd570b615")

# logging options
LOG_DIR = os.environ.get("LOG_DIR", "/home/app/log")
LOG_LEVEL = int(os.environ.get("LOG_LEVEL", logging.DEBUG))
LOG_ROTATE = bool(int(os.environ.get("LOG_ROTATE", 0)))
LOG_ROTATE_SIZE = os.environ.get("LOG_ROTATE_SIZE", 26214400)
LOG_ROTATE_COUNT = os.environ.get("LOG_ROTATE_COUNT", 3)

# app info
APP_VERSION = os.environ.get("APP_VERSION", app_vars["APP_VERSION"])
APP_ID = os.environ.get("APP_ID", app_vars["APP_ID"])
APP_VENDOR_DOMAIN = os.environ.get("APP_VENDOR_DOMAIN", 
                                        app_vars["APP_VENDOR_DOMAIN"])

# application running as an app on aci apic (ensure started file matches
# start.sh settings)
ACI_APP_MODE = bool(int(os.environ.get("ACI_APP_MODE",0)))
ACI_STARTED_FILE = os.environ.get("STARTED_FILE","/home/app/.started")
ACI_STATUS_FILE = os.environ.get("STATUS_FILE","/home/app/.status")


# default sender for email notifications
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "")

# enable/disable login for application. when login is disabled users are
# automatically allowed admin access
LOGIN_ENABLED = bool(int(os.environ.get("LOGIN_ENABLED",1)))

# simulate apic connection and callbacks for tests
SIMULATION_MODE = bool(int(os.environ.get("SIMULATION_MODE",0)))

