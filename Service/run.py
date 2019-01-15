# for local testing, when running in prod will use app.wsgi
from app import create_app
from app.models.utils import setup_logger
import logging
import os
import sys

logger = setup_logger(logging.getLogger("app"), stdout=True, quiet=True)

INFO = ["app.models.aci.tools"] 
for i in INFO: logging.getLogger(i).setLevel(logging.INFO)

def get_args():
    # get command line arguments

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", action="store", dest="port", type=int,
        default=80, help="start flask debug web server")
    parser.add_argument("-d", action="store", dest="debug", default="debug",
        help="debugging level", choices=["debug","info","warn","error"])
    parser.add_argument("--test", action="store_true", dest="test",
        help="run app in test module mode")
    args = parser.parse_args()

    # set debug level
    args.debug = args.debug.upper()
    if args.debug == "DEBUG": logger.setLevel(logging.DEBUG)
    if args.debug == "INFO": logger.setLevel(logging.INFO)
    if args.debug == "WARN": logger.setLevel(logging.WARN)
    if args.debug == "ERROR": logger.setLevel(logging.ERROR)
    return args

# instance relative config - config.py implies instance/config.py
if __name__ == "__main__":

    args = get_args()
    if args.test:
        # override some config settings and add test modules
        from tests.api.test_proxy import Rest_TestProxy
        app = create_app("config.py")
        app.config["LOGIN_ENABLED"] = False
        app.config["DEBUG"] = True
        app.config["MONGO_DBNAME"] = "testdb"
        app.config["TMP_DIR"] = os.path.realpath("%s/test" % app.config["TMP_DIR"])
    else:
        app = create_app("config.py")
    logger.debug("running on port %s" % args.port)
    app.run(host="0.0.0.0", port=args.port)


