
from flask import request
import random, string, time, logging, re, sys, json, datetime, traceback
from pymongo import MongoClient
from flask_bcrypt import generate_password_hash
import dateutil.parser

# module level logging
logger = logging.getLogger(__name__)

# common message
MSG_403 = "Sorry old chap, this is a restricted area..."

# track app so we don't need to create it multiple times
_g_app = None  
_g_app_config = None
_g_db = None
def get_app():
    global _g_app
    if _g_app is None: 
        # dynamically import only at first call
        from .. import create_app
        _g_app = create_app("config.py")
    return _g_app

def get_app_config():
    # return config dict from app
    global _g_app_config
    if _g_app_config is None:
        # dynamically import app config at first call
        from .. import create_app_config
        _g_app_config = create_app_config("config.py")
    return _g_app_config

def get_db(uniq=False, overwrite_global=False):
    # return instance of mongo db, set uniq to True to always return a uniq db connection
    # set uniq to True and overwrite_global to True to force new global db as well
    global _g_db
    if _g_db is None or uniq:
        config = get_app_config()
        db = config.get("MONGO_DBNAME", "devdb")
        if config.get("MONGO_WRITECONCERN", 0) == 0: w = 0
        else: w = 1
        uri = "mongodb://%s:%s/%s?" % (
            config.get("MONGO_HOST","localhost"),
            config.get("MONGO_PORT", 27017),
            db
        )
        if "MONGO_SERVER_SELECTION_TIMEOUT_MS" in config:
            uri+= "serverSelectionTimeoutMS=%s&" % (
                    config["MONGO_SERVER_SELECTION_TIMEOUT_MS"])
        if "MONGO_CONNECT_TIMEOUT_MS" in config:
            uri+= "connectTimeoutMS=%s&" % config["MONGO_CONNECT_TIMEOUT_MS"]
        if "MONGO_SOCKET_TIMEOUT_MS" in config:
            uri+= "socketTimeoutMS=%s&" % config["MONGO_SOCKET_TIMEOUT_MS"]
        uri = re.sub("[\?&]+$","",uri)
        logger.debug("starting mongo connection: %s", uri)
        client = MongoClient(uri, w=w)
        if _g_db is None or overwrite_global: _g_db = client[db]
        return client[db]
    return _g_db

###############################################################################
#
# common logging formats
#
###############################################################################

def setup_logger(logger, fname="utils.log", quiet=True, stdout=False, thread=False ):
    """ setup logger with appropriate logging level and rotate options """

    # quiet all other loggers...
    if quiet:
        old_logger = logging.getLogger()
        old_logger.setLevel(logging.CRITICAL)
        for h in list(old_logger.handlers): old_logger.removeHandler(h)
        old_logger.addHandler(logging.NullHandler())

    app_config = get_app_config()
    logger.setLevel(app_config["LOG_LEVEL"])
    try:
        if stdout:
            logger_handler = logging.StreamHandler(sys.stdout)
        elif app_config["LOG_ROTATE"]:
            logger_handler = logging.handlers.RotatingFileHandler(
                "%s/%s"%(app_config["LOG_DIR"],fname),
                maxBytes=app_config["LOG_ROTATE_SIZE"], 
                backupCount=app_config["LOG_ROTATE_COUNT"])
        else:
            logger_handler = logging.FileHandler(
                "%s/%s"%(app_config["LOG_DIR"],fname))
    except IOError as e:
        sys.stderr.write("failed to open logger handler: %s, resort stdout\n"%e)
        logger_handler = logging.StreamHandler(sys.stdout)
   
    if thread:
        fmt="%(process)d||%(threadName)s||%(asctime)s.%(msecs).03d||"
        fmt+="%(levelname)s||%(filename)s:(%(lineno)d)||%(message)s"
    else: 
        fmt ="%(process)d||%(asctime)s.%(msecs).03d||%(levelname)s||"
        fmt+="%(filename)s:(%(lineno)d)||%(message)s"
        
    logger_handler.setFormatter(logging.Formatter(
        fmt=fmt,
        datefmt="%Z %Y-%m-%d %H:%M:%S")
    )
    # remove previous handlers if present
    for h in list(logger.handlers): logger.removeHandler(h)
    logger.addHandler(logger_handler)
    return logger

###############################################################################
#
# misc/common functions
#
###############################################################################

def get_user_data():
    """ returns user provided json or empty dict """
    try:
        if not request.json: return {}
        ret = request.json
        if not isinstance(ret, dict): return {}
        return ret
    except Exception as e: return {}

def get_user_params():
    """ returns dict of user provided params """
    try:
        if not request.args: return {}
        ret = {}
        for k in request.args:
            ret[k] = request.args.get(k)
        return ret
    except Exception as e: return {}

def get_user_headers():
    """ return dict of user headers in http request """
    try:
        if not request.headers: return {}
        return request.headers
    except Exception as e: return {}

def get_user_cookies():
    """ return dict of user cookies indexed by cookie name """
    try:
        if not request.cookies: return {}
        return request.cookies
    except Exception as e: return {}

def hash_password(p):
    """ Return the bcrypt hash of the password 
        return None on failure
    """
    try:
        config = get_app_config()
        return generate_password_hash(p,config["BCRYPT_LOG_ROUNDS"])
    except Exception as e:
        logger.warn("failed to generate hash: %s" % e)

def aes_encrypt(data, **kwargs):
    # return AES encrypted data hexstring (None on failure)
    from Crypto.Cipher import AES
    import struct, binascii
    ekey = kwargs.get("ekey", None)
    eiv = kwargs.get("eiv", None)
    config = get_app_config()
    try:
        if ekey is None: ekey = config["EKEY"]
        if eiv is None: eiv = config["EIV"]
        ekey = ("%s" % ekey).decode("hex")
        eiv = ("%s" % eiv).decode("hex")
        ec = AES.new(ekey, AES.MODE_CBC, eiv)

        # pad data to 16 bytes (each pad byte is length of padding)
        # example - pad_count is 4.  Then pad "\x04\x04\x04\x04"
        data = data.encode("utf-8")
        pad_count = 16-len(data)%16
        data += struct.pack("B", pad_count)*pad_count
        # need to store data as hex string, so always return hex string
        edata = binascii.hexlify(ec.encrypt(data))
        return edata
    except Exception as e:
        logger.error("aes_encrypt %s" % e)

    return None
        
def aes_decrypt(edata, **kwargs):
    # return AES decrypted data from data hexstring (None on failure)
    from Crypto.Cipher import AES
    import struct, binascii
    ekey = kwargs.get("ekey", None)
    eiv = kwargs.get("eiv", None)
    config = get_app_config()
    try:
        if ekey is None: ekey = config["EKEY"]
        if eiv is None: eiv = config["EIV"]
        ekey = ("%s" % ekey).decode("hex")
        eiv = ("%s" % eiv).decode("hex")
        ec = AES.new(ekey, AES.MODE_CBC, eiv)

        # decrypt data hex string
        data = ec.decrypt(edata.decode("hex"))
        # need to remove padding from decrypted data - last byte should be
        # value between 0 and 15 representing number of characters to remove
        last_byte = ord(data[-1])
        if last_byte>0 and last_byte<=16 and len(data)>=last_byte:
            data = data[0:(len(data)-last_byte)]
        return data
    except Exception as e:
        logger.error("aes_decrypt error %s" % e)
    return None

def pretty_print(js):
    """ try to convert json to pretty-print format """
    try:
        return json.dumps(js, indent=4, separators=(",", ":"), sort_keys=True)
    except Exception as e:
        return "%s" % js

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
        _tz_string = "+%s:%s" % ('{0:>02d}'.format(ohour),
                           '{0:>02d}'.format(omin))
    else:
        _tz_string =  "-%s:%s" % ('{0:>02d}'.format(ohour),
                           '{0:>02d}'.format(omin))
    return _tz_string

def parse_timestamp(ts_str):
    """ return float unix timestamp for timestamp string """
    dt = dateutil.parser.parse(ts_str)
    return (time.mktime(dt.timetuple()) + dt.microsecond/1000000.0)

def format_timestamp(timestamp, msec=False):
    """ format timestamp to datetime string """

    datefmt="%Y-%m-%dT%H:%M:%S"
    try:
        t= datetime.datetime.fromtimestamp(int(timestamp)).strftime(datefmt)
        if msec:
            if timestamp == 0: t = "%s.000" % t
            else: t="{0}.{1:03d}".format(t, int((timestamp*1000)%1000))
        t = "%s%s" % (t, current_tz_string())
        return t
    except Exception as e:
        return timestamp

def get_timestamp(msec=False):
    """ get formatted timestamp """
    return format_timestamp(time.time(), msec=msec)

def list_routes(app, api=False):
    """ list all current app routes - debugging only
        http://flask.pocoo.org/snippets/117/
    """
    import urllib
    from flask import url_for
    output = []
    for rule in app.url_map.iter_rules():
        options = {}
        for arg in rule.arguments:
            options[arg] = "[{0}]".format(arg)

        methods = ','.join(rule.methods)
        l = "{:50s} {:30s} {}".format(rule.endpoint, methods, rule)
        if l not in output: output.append(l)
    
    routes = sorted(output)

    if api: return routes
    for line in routes: print line
