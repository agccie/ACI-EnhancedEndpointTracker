# for local testing
from app import create_app

import logging, sys
logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)
logger_handler = logging.StreamHandler(sys.stdout)
fmt ="%(asctime)s.%(msecs).03d||%(levelname)s||%(filename)s"
fmt+=":(%(lineno)d)||%(message)s"
logger_handler.setFormatter(logging.Formatter(
    fmt=fmt,
    datefmt="%Z %Y-%m-%d %H:%M:%S")
)
logger.addHandler(logger_handler)

def get_args():
    # get command line arguments

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", action="store", dest="port", type=int,
        help="start manager")
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
    app.run(host="0.0.0.0", port=args.port)
