
import sys, os, logging, logging.handlers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models.utils import setup_logger
setup_logger(logging.getLogger("app"), quiet=True)
INFO = ["app.models.aci.tools"] 
for i in INFO: logging.getLogger(i).setLevel(logging.INFO)
app = create_app("config.py")

# flask requires 'application' variable from wsgi module
application = app

