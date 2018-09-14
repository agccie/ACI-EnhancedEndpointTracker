"""
Script to deploy app on Docker swarm
"""
import argparse
import logging
import os
import sys
import traceback

# update path to allow for semi-relatively imports
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

from deploy.cluster_config import ClusterConfig

logger = logging.getLogger(__name__)

def setup_logger(logger, loglevel="debug", logfile="/tmp/deploy.log"):
    """ setup two loggers, one to stdout with user provided logging level and second to file with 
        full debug enabled
    """

    fmt ="%(process)d||%(asctime)s.%(msecs).03d||%(levelname)s||"
    fmt+="%(filename)s:(%(lineno)d)||%(message)s"
    datefmt="%Z %Y-%m-%d %H:%M:%S"

    # quiet all other loggers...
    old_logger = logging.getLogger()
    old_logger.setLevel(logging.CRITICAL)
    for h in list(old_logger.handlers): old_logger.removeHandler(h)
    old_logger.addHandler(logging.NullHandler())
    for h in list(logger.handlers): logger.removeHandler(h)
    
    logger.setLevel(logging.DEBUG)

    # stream handler to stdout at user provided log level
    fmt ="%(asctime)s.%(msecs).03d||%(levelname)s||%(message)s"
    shandler = logging.StreamHandler(sys.stdout)
    shandler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    loglevel = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "error": logging.ERROR
    }.get(loglevel, logging.DEBUG)
    shandler.setLevel(loglevel)
    logger.addHandler(shandler)

    # write full debug file to logfile
    try:
        fmt ="%(process)d||%(asctime)s.%(msecs).03d||%(levelname)s||"
        fmt+="%(filename)s:(%(lineno)d)||%(message)s"
        fhandler = logging.FileHandler(logfile)
        fhandler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
        fhandler.setLevel(logging.DEBUG)
        #logger.addHandler(fhandler)
    except IOEerror as e:
        sys.stderr.write("failed to open logger handler: %s\n" % logfile)
    return logger

if __name__ == "__main__":

    default_config = "%s/config.yml" %os.path.dirname(os.path.realpath(__file__))
    desc = __doc__
    parser = argparse.ArgumentParser(description=desc, 
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-c","--config", dest="config", help="cluster config file in yaml format",
            default=default_config)
    parser.add_argument("-d","--debug", dest="debug", choices=["debug","info","warn","error"],
        help="debug loglevel", default="debug")
    parser.add_argument("-l","--log", dest="logfile", default="/tmp/deploy.log", help="log file")
    args = parser.parse_args()

    # setup logging
    logger = setup_logger(logger, loglevel=args.debug, logfile=args.logfile)
    setup_logger(logging.getLogger("deploy"), loglevel=args.debug, logfile=args.logfile)

    # validate config file
    config = ClusterConfig()
    try:
        config.import_config(args.config)
        config.build_compose()
    except Exception as e:
        logger.debug("Traceback:\n%s", traceback.format_exc())
        logger.error("Unable to deploy cluster: %s", e)
        sys.exit(1)

    logger.debug("deployment complete")


