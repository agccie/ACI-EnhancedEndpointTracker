
# for local testing, when running in prod will use app.wsgi
from app import create_app
from app.tasks.ept.utils import setup_logger

import logging, sys
logger = setup_logger(logging.getLogger("app"),stdout=True, quiet=True)

def get_args():
    # get command line arguments

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", action="store", dest="port", type=int,
        default=80, help="start flask debug web server")
    parser.add_argument("-d", action="store", dest="debug", default="debug",
        help="debugging level", choices=["debug","info","warn","error"])
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
    app = create_app("config.py")
    logger.debug("running on port %s" % args.port)
    app.run(host="0.0.0.0", port=args.port)


