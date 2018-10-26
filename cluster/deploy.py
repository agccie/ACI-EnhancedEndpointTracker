"""
Script to deploy app on Docker swarm or create kron config
"""
import argparse
import logging
import os
import sys
import traceback

# update path to allow for semi-relatively imports
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

from pkg.cluster_config import ClusterConfig
from pkg.swarmer import Swarmer

logger = logging.getLogger(__name__)

def setup_logger(logger, loglevel="debug", logfile=None):
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
    if logfile is not None:
        try:
            fmt ="%(process)d||%(asctime)s.%(msecs).03d||%(levelname)s||"
            fmt+="%(filename)s:(%(lineno)d)||%(message)s"
            fhandler = logging.FileHandler(logfile)
            fhandler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
            fhandler.setLevel(logging.DEBUG)
            logger.addHandler(fhandler) 
            # logger needs to have level set to DEBUG so debugs go to filehandler
            logger.setLevel(logging.DEBUG) 
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
        help="debug loglevel", default="info")
    parser.add_argument("-l","--log", dest="logfile", default="/tmp/deploy.log", help="log file")
    parser.add_argument("-u","--username", dest="username", 
        help="username for initializing other nodes within the cluster")
    parser.add_argument("-p","--password", dest="password", 
        help="password for initializing other nodes within the cluster")

    args = parser.parse_args()

    # setup logging
    logger = setup_logger(logger, loglevel=args.debug, logfile=args.logfile)
    setup_logger(logging.getLogger("pkg"), loglevel=args.debug, logfile=args.logfile)
    setup_logger(logging.getLogger("pkg.connection"), loglevel="info", logfile=None)
    logger.info("Logfile: %s", args.logfile)

    # validate config file
    config = ClusterConfig()
    try:
        config.import_config(args.config)
        config.build_compose()
        swarm = Swarmer(config, username=args.username, password=args.password)
        swarm.init_swarm()
        swarm.deploy_service()
        swarm.init_db()
        logger.info("deployment complete")
    except Exception as e:
        logger.debug("Traceback:\n%s", traceback.format_exc())
        logger.error("Unable to deploy cluster: %s", e)
        sys.exit(1)
    except KeyboardInterrupt as e:
        logger.debug("keyboard interrupt")
        print "\nBye!"
        sys.exit(1)


