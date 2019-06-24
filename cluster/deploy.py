"""
Script to deploy app on Docker swarm
"""
import argparse
import json
import logging
import os
import re
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

    datefmt="%Z %Y-%m-%d %H:%M:%S"

    # quiet all other loggers...
    old_logger = logging.getLogger()
    old_logger.setLevel(logging.CRITICAL)
    for h in list(old_logger.handlers): old_logger.removeHandler(h)
    old_logger.addHandler(logging.NullHandler())
    for h in list(logger.handlers): logger.removeHandler(h)
    
    # stream handler to stdout at user provided log level
    fmt ="%(asctime)s.%(msecs).03d||%(levelname)s||%(message)s"
    if loglevel == "debug":
        fmt ="%(process)d||%(asctime)s.%(msecs).03d||%(levelname)s||"
        fmt+="%(filename)s:(%(lineno)d)||%(message)s"

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
        except IOError as e:
            sys.stderr.write("failed to open logger handler: %s\n" % logfile)
    return logger

def prompt_user_for_node_count():
    """ prompt user for node count and return interger number of nodes """
    default_count = 1
    while True:
        node_count = raw_input("Number of nodes in cluster [%s]: " % default_count).strip()
        if re.search("^[0-9]+$", node_count) and int(node_count)<ClusterConfig.MAX_NODES:
            return int(node_count)
        elif len(node_count) == 0:
            return default_count
        else:
            print("Invalid value(%s) for node. Please choose a value between 1 and %s" % (
                node_count, ClusterConfig.MAX_NODES))

if __name__ == "__main__":

    # parse app.json for container info
    app_config = os.path.abspath("%s/../app.json" % os.path.dirname(os.path.realpath(__file__)))
    default_config = "%s/swarm/swarm_config.yml" %os.path.dirname(os.path.realpath(__file__))

    # parse app_config first to get container base name and app name
    app_id = None
    app_container_namespace = None
    app_version = None
    app_name = None
    if os.path.exists(app_config):
        try:
            with open(app_config, "r") as f:
                js = json.load(f)
                for r in ["appid", "full_version", "container_namespace", "short_name"]:
                    if r not in js:
                        raise Exception("%s missing required attribute %s" % (app_config, r))
                app_id = js["appid"]
                app_version = js["full_version"]
                app_container_namespace = js["container_namespace"]
                app_name = js["short_name"]
                app_image_base = ("%s/%s" % (app_container_namespace, app_id)).lower()
        except Exception as e:
            print("exception parsing app config: %s" % e)
            sys.exit(1)
    else:
        print("required file missing: %s" % app_config)
        sys.exit(1)

    parser = argparse.ArgumentParser(description=__doc__, 
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v","--version",
        dest="version",
        default=app_version,
        help="Container version to deploy. Default '%s'" % app_version
    )
    parser.add_argument(
        "--name",
        dest="name",
        default=app_name,
        help="app service short name (default '%s')" % app_name,
    )
    parser.add_argument(
       "--worker",
       dest="worker_count",
       metavar="N",
       default=None,
       type=int,
       help="the number worker processes",
    )
    parser.add_argument(
        "--db_shard",
        dest="db_shard",
        metavar="N",
        default=None,
        type=int,
        help="the number db shards to deploy",
    )
    parser.add_argument(
        "--db_replica",
        dest="db_replica",
        metavar="N",
        default=None,
        type=int,
        help="the number of replicas per db shard and db configsvr",
    )
    parser.add_argument(
        "--db_memory",
        dest="db_memory",
        metavar="N",
        default=None,
        type=float,
        help="the maximium memory allowed per db process",
    )
    parser.add_argument(
        "--swarm_config",
        dest="swarm_config",
        default=default_config,
        help="""path to swarm configuration file (default: %s)""" % default_config
    )
    parser.add_argument(
        "-n","--nodes",
        dest="nodes",
        metavar="N",
        default=None,
        type=int,
        help="number of nodes in the cluster (default 1 node)"
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
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--techsupport",
        dest="techsupport",
        action="store_true",
        help="""initiate techsupport collection across all nodes within the cluster""",
    )
    actions.add_argument(
        "--config",
        dest="config",
        action="store_true",
        help="""create the compose file for deploying the stack""",
    )
    actions.add_argument(
        "--deploy",
        dest="deploy",
        action="store_true",
        help="""initialize swarm and deploy stack"""
    )
    actions.add_argument(
        "--wipe",
        dest="wipe",
        action="store_true",
        help="""remove stack and clean up all containers and storage volumes"""
    )
    args = parser.parse_args()

    # setup logging
    logger = setup_logger(logger, loglevel=args.debug, logfile=args.logfile)
    setup_logger(logging.getLogger("swarm"), loglevel=args.debug, logfile=args.logfile)
    setup_logger(logging.getLogger("swarm.connection"), loglevel="info", logfile=None)
    logger.debug("Logfile: %s", args.logfile)

    # validate a few config arguments if provided
    try:
        if args.worker_count is not None and args.worker_count > ClusterConfig.MAX_WORKERS:
            raise Exception("invalid worker count %s, must be <= %s" % (args.worker_count, 
                            ClusterConfig.MAX_WORKERS))
        if args.db_shard is not None and args.db_shard > ClusterConfig.MAX_SHARDS:
            raise Exception("invalid shard count %s, must be <= %s" % (args.db_shard, 
                            ClusterConfig.MAX_SHARDS))
        if args.db_replica is not None and args.db_replica > ClusterConfig.MAX_REPLICAS:
            raise Exception("invalid shard count %s, must be <= %s" % (args.db_replica, 
                            ClusterConfig.MAX_REPLICAS))
        if args.db_memory is not None and args.db_memory > ClusterConfig.MAX_MEMORY:
            raise Exception("invalid shard count %s, must be <= %s" % (args.db_memory, 
                            ClusterConfig.MAX_MEMORY))
    except Exception as e:
        logger.error("Invalid argument. %s", e)
        sys.exit(1)

    try:
        image = "%s:%s" % (app_image_base, args.version)
        # for create config and deploy, we need to get the number of intended nodes.
        if args.nodes is None:
            if args.deploy or args.config:
                args.nodes = prompt_user_for_node_count()
            else:
                args.nodes = 1

        # validate config file
        config = ClusterConfig(image, 
                    node_count=args.nodes, 
                    app_name=args.name,
                    worker_count=args.worker_count,
                    db_shard=args.db_shard,
                    db_replica=args.db_replica,
                    db_memory=args.db_memory
                )

        # all actions (techsupport/config/init/deploy) all required configuration to be parsed
        if args.config:
            config.import_config(args.swarm_config)
            config.build_compose()
        elif args.deploy:
            config.import_config(args.swarm_config)
            config.build_compose()
            swarm = Swarmer(config, username=args.username, password=args.password)
            swarm.init_swarm()
            swarm.deploy_service()
            logger.info("deployment complete")
        elif args.techsupport:
            swarm = Swarmer(config, username=args.username, password=args.password)
            swarm.collect_techsupport(logfile=args.logfile)
        elif args.wipe:
            # confirm user really wants to proceed:
            confirm = None
            while confirm is None:
                msg = "This action will delete the stack and remove all containers and data. "
                msg+= "This action cannot be undone.\nAre you sure you want to proceed [y/N]: "
                confirm = raw_input(msg).strip().lower()
                if confirm == "y" or confirm == "yes":
                    config.import_config(args.swarm_config)
                    swarm = Swarmer(config, username=args.username, password=args.password)
                    swarm.wipe()
                elif len(confirm) == 0 or confirm == "n" or confirm == "no":
                    # if the length is 0 then implicit no
                    pass
                else:
                    print("invalid option '%s'" % confirm)
                    confirm = None
    except Exception as e:
        logger.debug("Traceback:\n%s", traceback.format_exc())
        logger.error("Unable to deploy cluster: %s", e)
        sys.exit(1)
    except KeyboardInterrupt as e:
        logger.debug("keyboard interrupt")
        print "\nBye!"
        sys.exit(1)


