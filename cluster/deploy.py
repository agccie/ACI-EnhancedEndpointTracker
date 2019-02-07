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

from swarm.create_config import ClusterConfig
from swarm.swarmer import Swarmer

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

    default_config = "%s/swarm/swarm_config.yml" %os.path.dirname(os.path.realpath(__file__))
    parser = argparse.ArgumentParser(description=__doc__, 
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-c","--config", 
        dest="config", 
        default=default_config,
        help="cluster config file in yaml format",
    )
    parser.add_argument(
        "-a","--action",
        dest="action",
        choices=["config", "deploy", "techsupport"],
        default="deploy",
        help="""the deploy script can be used to creat the compose file (config), along with 
                initializing the swarm and deploying the stack (deploy).
                User can also specify (techsupport) to collect app techsupport logs.
            """,
    )
    parser.add_argument(
        "-u","--username", 
        dest="username", 
        help="username for connecting to other nodes within the cluster used by init/ts actions",
    )
    parser.add_argument(
        "-p","--password", 
        dest="password", 
        help="password for connecting to other nodes within the cluster used by init/ts actions",
    )
    parser.add_argument(
        "-d","--debug", 
        dest="debug", 
        choices=["debug","info","warn","error"],
        default="info",
        help="debug loglevel", 
    )
    parser.add_argument(
        "-l","--log", 
        dest="logfile", 
        default="/tmp/deploy.log", 
        help="log file",
    )


    args = parser.parse_args()

    # setup logging
    logger = setup_logger(logger, loglevel=args.debug, logfile=args.logfile)
    setup_logger(logging.getLogger("swarm"), loglevel=args.debug, logfile=args.logfile)
    setup_logger(logging.getLogger("swarm.connection"), loglevel="info", logfile=None)
    logger.info("Logfile: %s", args.logfile)

    # validate config file
    config = ClusterConfig()
    try:
        # all actions (techsupport/config/init/deploy) all required configuration to be parsed
        config.import_config(args.config)
        config.build_compose()
        if args.action == "config":
            logger.info("configuration build complete")
        elif args.action == "deploy":
            swarm = Swarmer(config, username=args.username, password=args.password)
            swarm.init_swarm()
            swarm.deploy_service()
            logger.info("deployment complete")
        elif args.action == "techsupport":
            logger.info("collection techsupport")
    except Exception as e:
        logger.debug("Traceback:\n%s", traceback.format_exc())
        logger.error("Unable to deploy cluster: %s", e)
        sys.exit(1)
    except KeyboardInterrupt as e:
        logger.debug("keyboard interrupt")
        print "\nBye!"
        sys.exit(1)


