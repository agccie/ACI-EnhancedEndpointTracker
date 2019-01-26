from datetime import timedelta
from multiprocessing import cpu_count

import json
import logging
import os
import sys

# these variables are set from app.json if found. Use app.json as single
# source of truth.
app_vars = {
    "APP_VENDOR_DOMAIN":    "Cisco",
    "APP_ID":               "ExampleApp",
    "APP_CONTACT_EMAIL":    "",
    "APP_CONTACT_URL":      "",
    "APP_VERSION":          "1.0",
    "APP_COMMIT":           "",
    "APP_COMMIT_DATE":      "",
    "APP_COMMIT_DATE_EPOCH": 0,
    "APP_COMMIT_AUTHOR":    "",
    "APP_COMMIT_BRANCH":    "",
    "APP_FULL_VERSION":     "",
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
                app_vars["APP_VERSION"] = js["version"]
            if "full_version" in js:
                app_vars["APP_FULL_VERSION"] = js["full_version"]
            else:
                app_vars["APP_FULL_VERSION"] = app_vars["APP_VERSION"]
            if "contact" in js:
                if "contact-email" in js["contact"]:
                    app_vars["APP_CONTACT_EMAIL"] = js["contact"]["contact-email"]
                if "contact-url" in js["contact"]:
                    app_vars["APP_CONTACT_URL"] = js["contact"]["contact-url"]
    except Exception as e: pass

# version.txt is created at build and should be in the following format
# 923797471c147b67b1e71004a8873d61db8d8f82
# 2018-09-27T10:12:48-04:00
# 1538057568
# agccie@users.noreply.github.com
# master
version_file = "%s/version.txt" % os.path.dirname(os.path.realpath(__file__))
if os.path.exists(version_file):
    try:
        with open(version_file, "r") as f:
            lines = f.readlines()
            if len(lines) >= 5:
                app_vars["APP_COMMIT"] = lines[0].strip()
                app_vars["APP_COMMIT_DATE"] = lines[1].strip()
                app_vars["APP_COMMIT_DATE_EPOCH"] = lines[2].strip()
                app_vars["APP_COMMIT_AUTHOR"] = lines[3].strip()
                app_vars["APP_COMMIT_BRANCH"] = lines[4].strip()
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
MONGO_WRITECONCERN = int(os.environ.get("MONGO_WRITECONCERN",1))

# enable application debugging (ensure debugging is disabled on production app)
DEBUG = bool(int(os.environ.get("DEBUG", 1)))

# disable pretty print by default to help with large repsonses
JSONIFY_PRETTYPRINT_REGULAR = bool(int(
                            os.environ.get("JSONIFY_PRETTYPRINT_REGULAR",0)))

# authentication settings
REMEMBER_COOKIE_DURATION = timedelta(days=int(os.environ.get("REMEMBER_COOKIE_DURATION",0)))
BCRYPT_LOG_ROUNDS = 12
LOGIN_ENABLED = bool(int(os.environ.get("LOGIN_ENABLED",1)))
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

# start all configured monitors when container starts
AUTO_START_MONITOR = bool(int(os.environ.get("AUTO_START_MONITOR",1)))

# app info
APP_VERSION = os.environ.get("APP_VERSION", app_vars["APP_VERSION"])
APP_ID = os.environ.get("APP_ID", app_vars["APP_ID"])
APP_VENDOR_DOMAIN = os.environ.get("APP_VENDOR_DOMAIN", app_vars["APP_VENDOR_DOMAIN"])
APP_CONTACT_URL = os.environ.get("APP_CONTACT_URL", app_vars["APP_CONTACT_URL"])
APP_CONTACT_EMAIL = os.environ.get("APP_CONTACT_EMAIL", app_vars["APP_CONTACT_EMAIL"])
APP_FULL_VERSION = app_vars["APP_FULL_VERSION"]
APP_COMMIT = app_vars["APP_COMMIT"]
APP_COMMIT_DATE = app_vars["APP_COMMIT_DATE"]
APP_COMMIT_DATE_EPOCH = app_vars["APP_COMMIT_DATE_EPOCH"]
APP_COMMIT_AUTHOR = app_vars["APP_COMMIT_AUTHOR"]
APP_COMMIT_BRANCH = app_vars["APP_COMMIT_BRANCH"]

# application running as an app on aci apic (ensure started file matches
# start.sh settings)
ACI_APP_MODE = bool(int(os.environ.get("ACI_APP_MODE",0)))
ACI_STARTED_FILE = os.environ.get("STARTED_FILE","/home/app/.started")
ACI_STATUS_FILE = os.environ.get("STATUS_FILE","/home/app/.status")

# set maximum file size for uploads (default to 10G)
MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 10*1024*1024*1024))

# tmp directory for working with tmp files (and uploaded files)
TMP_DIR = os.environ.get("TMP_DIR", "/tmp/")
MAX_POOL_SIZE = int(os.environ.get("MAX_POOL_SIZE", cpu_count()))

# redis config
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))

# email options
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "noreply@aci.app")

# set to APIC in APP_MODE=1 and executing on app-infra supported apic (4.0+)
HOSTED_PLATFORM = os.environ.get("HOSTED_PLATFORM","")

