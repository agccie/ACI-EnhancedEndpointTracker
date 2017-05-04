import os, logging
from datetime import timedelta

# specify mongo uri
#   mongodb://[username:password@]host1[:port1][,host2[:port2],\
#    ...[,hostN[:portN]]][/[database][?options]]
MONGO_URI = os.environ.get('MONGO_URI', 
    "mongodb://localhost:27017/devdb?connectTimeoutMS=100&socketTimeoutMS=60000&serverSelectionTimeoutMS=5000")

# enable application debugging (ensure debugging is disabled on production app)
DEBUG = bool(int(os.environ.get("DEBUG", 1)))

# secret key for secret functions...
SECRET_KEY = os.environ.get("SECRET_KEY", "d41d8cd98f00b204e9800998ecf8427e")
EKEY = os.environ.get("EKEY", "A90DF148C0B6B383754224B2EB720C02")
EIV  = os.environ.get("EIV", "B1CEF3F0708FA29EBDB86A9E41B80CA2")

# length of time cookie is set to valid on client
REMEMBER_COOKIE_DURATION = timedelta(
    days=int(os.environ.get("REMEMBER_COOKIE_DURATION",1)))

# Enable SSO authentication (requires webserver reload for changes to apply)
SSO_ENABLED = bool(int(os.environ.get("SSO_ENABLED", 0)))

# bcrypt rounds (can theoretically be changed live without affecting existing)
BCRYPT_LOG_ROUNDS = 12

# default sender for email notifications
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "")

# logging options
LOG_DIR = os.environ.get("LOG_DIR", "/var/log/ept/")
LOG_LEVEL = int(os.environ.get("LOG_LEVEL", logging.DEBUG))
LOG_ROTATE = bool(int(os.environ.get("LOG_ROTATE", 1)))
LOG_ROTATE_SIZE = os.environ.get("LOG_ROTATE_SIZE", 26214400)
LOG_ROTATE_COUNT = os.environ.get("LOG_ROTATE_COUNT", 3)

# enable/disable login for application.  when login is disabled users are
# automatically allowed admin access
LOGIN_ENABLED = bool(int(os.environ.get("LOGIN_ENABLED",1)))

# url for proxy function
PROXY_URL = os.environ.get("PROXY_URL", "http://127.0.0.1:80/")

# simulate apic connection and callbacks
SIMULATION_MODE = bool(int(os.environ.get("SIMULATION_MODE",0)))

# application running as an app on aci apic (ensure started file matches 
# start.sh settings)
ACI_APP_MODE = bool(int(os.environ.get("ACI_APP_MODE",0)))
ACI_STARTED_FILE = os.environ.get("ACI_STARTED_FILE","/home/app/data/.started")
