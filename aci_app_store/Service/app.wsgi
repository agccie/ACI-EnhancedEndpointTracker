
import sys, os, logging, logging.handlers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
app = create_app("config.py")

# setup logging 
logger = logging.getLogger("app")
logger.setLevel(app.config["LOG_LEVEL"])
if app.config["LOG_ROTATE"]:
    logger_handler = logging.handlers.RotatingFileHandler(
        "%s/%s"%(app.config["LOG_DIR"],"wsgi.log"),
        maxBytes=app.config["LOG_ROTATE_SIZE"], 
        backupCount=app.config["LOG_ROTATE_COUNT"])
else:
    logger_handler = logging.FileHandler(
        "%s/%s"%(app.config["LOG_DIR"],"wsgi.log"))
fmt ="%(process)d||%(asctime)s.%(msecs).03d||%(levelname)s||%(filename)s"
fmt+=":(%(lineno)d)||%(message)s"
logger_handler.setFormatter(logging.Formatter(
    fmt=fmt,
    datefmt="%Z %Y-%m-%d %H:%M:%S")
)
logger.addHandler(logger_handler)

# flask requires 'application' variable from wsgi module
application = app

