import copy
import logging
import os
import re
import yaml

logger = logging.getLogger(__name__)

class ClusterConfig(object):
    """ manage parsing user config.yml to swarm compose file """

    APP_IMAGE = "agccie/enhancedendpointtracker:latest"

    # limits to prevent accidental overprovisioning
    MAX_NODES = 10
    MAX_WORKERS = 128
    MAX_WATCHERS = 4
    MIN_PREFIX = 8
    MAX_PREFIX = 27
    MAX_SHARDS = 32
    MAX_REPLICAS = 9
    MAX_MEMORY = 512

    # everything has the same logging limits for now
    LOGGING_MAX_SIZE = "50m"
    LOGGING_MAX_FILE = "10"

    def __init__(self):
        self.nodes = {}         # indexed by node id, {"id":int, "hostname":"addr"}
        self.app_workers = 5
        self.app_watchers = 1
        self.app_subnet = "192.0.2.0/27"
        self.app_name = "ept"
        # set http/https port to 0 to disable that service
        self.app_http_port = 80
        self.app_https_port = 443
        self.redis_port = 6379
        self.mongos_port = 27017
        self.configsvr_port = 27019
        self.shardsvr_port = 27017
        self.shardsvr_shards = 1
        self.shardsvr_memory = 2.0
        self.shardsvr_replicas = 1
        self.configsvr_memory = 2.0
        self.configsvr_replicas = 1
        self.logging_stdout = False
        self.compose_file = "/tmp/compose.yml"
        self.services = {}         # indexed by service name and contains node label or 0

    def import_config(self, configfile):
        """ import/parse and validate config file, raise exception on error """
        logger.info("loading config file: %s", configfile)
        with open(configfile, "r") as f:
            try:
                config = yaml.load(f)
            except yaml.parser.ParserError as e:
                logger.debug(e)
                raise Exception("failed to parse config file")
            # walk through keys, fail if there are any unexpected keys so user knows the config is
            # invalid (this is better than sliently ignoring a configuration user is trying to make)
            for k in config:
                if k == "nodes":
                    self.add_nodes(config[k])
                elif k == "app":
                    self.add_app(config[k])
                elif k == "database":
                    self.add_database(config[k])
                elif k == "logging":
                    self.add_logging(config[k])
                else:
                    logger.info("unexpected key '%s'", k)
                    raise Exception("invalid config file")
        # majority of validation has already been performed. Last step is to validate nodes are 
        # contiguous, start at '1', and '1' is localhost or 127.0.0.1 
        node_ids = self.nodes.keys()
        for i in xrange(1, max(self.nodes.keys())+1):
            if i not in self.nodes:
                raise Exception("expected node id '%s' in list of nodes between 1 and %s" % (
                    i, max(self.nodes.keys())))

        # node-1 can be any address, should be localhost but not enforced
        #if self.nodes[1]["hostname"] != "localhost" and self.nodes[1]["hostname"] != "127.0.0.1":
        #    raise Exception("node 1 (%s) must have hostname 'localhost'"%self.nodes[1]["hostname"])

        # ensure that there are no duplicate IPs
        index_hostname = {}
        for nid in self.nodes:
            if self.nodes[nid]["hostname"] in index_hostname:
                raise Exception("duplicate node hostname: %s" % self.nodes[nid]["hostname"])

        # ensure that shardsvr_replicas is <= number of nodes
        if self.shardsvr_replicas > len(self.nodes):
            raise Exception("shardsvr replica (%s) must be less than numer of nodes (%s)" % (
                self.shardsvr_replicas, len(self.nodes)))

        # ensure that configsvr_replicas is <= number of nodes
        if self.configsvr_replicas > len(self.nodes):
            raise Exception("configsvr replica (%s) must be less than numer of nodes (%s)" % (
                self.configsvr_replicas, len(self.nodes)))

    def add_nodes(self, config):
        """ add one or more nodes from config """
        logger.debug("add nodes to config: %s", config)
        if type(config) is not list:
            raise Exception("nodes must be a list")
        for n in config:
            # expect only id and hostname within node config
            if "id" not in n:
                raise Exception("'id' field required in each node")
            if "hostname" not in n:
                raise Exception("'hostname' field required in each node")
            node = {"id": 0, "hostname": ""}
            for k in n:
                if k not in node: raise Exception("unexpected attribute '%s' for node" % k)
                node[k] = n[k]
            if type(node["id"]) is not int or node["id"]<1 or node["id"] > ClusterConfig.MAX_NODES:
                raise Exception("invalid node id '%s', should be an integer between 1 and %s" % (
                    node["id"], ClusterConfig.MAX_NODES))
            self.nodes[node["id"]] = node
            logger.debug("adding node_id %s = %s", node["id"], node["hostname"])

    def add_app(self, config):
        """ add app attributes from config """
        logger.debug("adding app config: %s", config)
        for k in config:
            if k == "workers": 
                if type(config[k]) is not int or config[k] > ClusterConfig.MAX_WORKERS:
                    raise Exception("invalid worker count '%s', should be between 1 and %s" % (
                        config[k], ClusterConfig.MAX_WORKERS))
                self.app_workers = config[k]
                logger.debug("setting app_worker count to %s", self.app_workers)
            elif k == "subnet":
                subnet = "%s" % config[k]
                r1 = re.search("^([0-9]+\.){3}[0-9]+/(?P<prefix>[0-9]+)$", subnet)
                if r1 is None:
                    raise Exception("invalid subnet '%s'" % subnet)
                subnet_prefix = int(r1.group("prefix"))
                if subnet_prefix > ClusterConfig.MAX_PREFIX or \
                    subnet_prefix < ClusterConfig.MIN_PREFIX:
                    raise Exception("invalid subnet prefix '%s', expected mask between %s and %s"%(
                        subnet_prefix, ClusterConfig.MIN_PREFIX, ClusterConfig.MAX_PREFIX))
                self.app_subnet = subnet
                logger.debug("setting app_subnet to %s", self.app_subnet)
            elif k == "name":
                self.app_name = config[k]
            elif k == "http_port":
                if type(config[k]) is not int or config[k]<0 or config[k]>0xffff:
                    raise Exception("invalid http port %s, must be between 1 and 65535"%config[k])
                self.app_http_port = config[k]
            elif k == "https_port":
                if type(config[k]) is not int or config[k]<0 or config[k]>0xffff:
                    raise Exception("invalid https port %s, must be between 1 and 65535"%config[k])
                self.app_https_port = config[k]
            else:
                raise Exception("unexpected attribute '%s' for app" % k)

    def add_database(self, config):
        """ add database attributes from config """
        logger.debug("adding database config: %s", config)
        for k in config:
            if k == "shardsvr": 
                self.add_shardsvr(config[k])
            elif k == "configsvr":
                self.add_configsvr(config[k])
            else:
                raise Exception("unexpected attribute '%s' for database" % k)

    def add_shardsvr(self, config):
        """ add shardsvr attributes from config """
        logger.debug("adding shardsvr config: %s", config)
        for k in config:
            if k == "shards": 
                if type(config[k]) is not int or config[k]<1 or config[k]>ClusterConfig.MAX_SHARDS:
                    raise Exception("invalid shard count '%s', expected between 1 and %s" % (
                        config[k], ClusterConfig.MAX_SHARDS))
                self.shardsvr_shards = config[k]
            elif k == "memory":
                if (type(config[k]) is not int and type(config[k]) is not float) or \
                    config[k] <= 0 or config[k] > ClusterConfig.MAX_MEMORY:
                    raise Exception("invalid shard memory threshold %s, expected between 1G and %sG"%(
                        config[k], ClusterConfig.MAX_MEMORY))
                self.shardsvr_memory = float(config[k])
            elif k == "replicas":
                if type(config[k]) is not int or config[k]<1 or config[k]>ClusterConfig.MAX_REPLICAS:
                    raise Exception("invalid shard replica count %s, expected between 1 and %s"%(
                        config[k], ClusterConfig.MAX_REPLICAS))
                self.shardsvr_replicas = config[k]
            else:
                raise Exception("unexpected attribute '%s' for shardsvr" % k)

    def add_configsvr(self, config):
        """ add configsvr attributes from config """
        logger.debug("adding configsvr config: %s", config)
        for k in config:
            if k == "memory":
                if (type(config[k]) is not int and type(config[k]) is not float) or \
                    config[k] <= 0 or config[k] > ClusterConfig.MAX_MEMORY:
                    raise Exception("invalid configsvr memory threshold %s, expected between 1G and %sG"%(
                        config[k], ClusterConfig.MAX_MEMORY))
                self.configsvr_memory = float(config[k])
            elif k == "replicas":
                if type(config[k]) is not int or config[k]<1 or config[k]>ClusterConfig.MAX_REPLICAS:
                    raise Exception("invalid configsvr replica count %s, expected between 1 and %s"%(
                        config[k], ClusterConfig.MAX_REPLICAS))
                self.configsvr_replicas = config[k]
            else:
                raise Exception("unexpected attribute '%s' for configsvr" % k)

    def add_logging(self, config):
        """ add logging attribute from config """
        logger.debug("adding logging config: %s", config)
        for k in config:
            if k == "stdout":
                if type(config[k]) is bool:
                    self.logging_stdout = config[k]
                elif type(config[k]) is int or type(config[k]) is float:
                    self.logging_stdout = config[k] > 0
                else:
                    raise Exception("invalid logging stdout value %s" % config[k])
            else:
                raise Exception("unexpected attribute '%s' for logging" % k)

    def get_shared_environment(self):
        """ return shared environment list """
        node_count = len(self.nodes)
        shared_environment = {
            "HOSTED_PLATFORM": "SWARM",
            "REDIS_HOST": "redis",
            "REDIS_PORT": self.redis_port,
            "DB_SHARD_COUNT": self.shardsvr_shards,
            "MONGO_HOST": "db",
            "MONGO_PORT": self.mongos_port,
        }
        cfg_svr = []
        for i in xrange(0, self.configsvr_replicas):
            cfg_svr.append("db_cfg_%s:%s" % (i, self.configsvr_port))
        shared_environment["DB_CFG_SRV"] = "cfg/%s" % (",".join(cfg_svr))

        for s in xrange(0, self.shardsvr_shards):
            rs = []
            for r in xrange(0, self.shardsvr_replicas):
                rs.append("db_sh_%s_%s:%s" % (s, r, self.shardsvr_port))
            shared_environment["DB_RS_SHARD_%s" % s ] = "sh%s/%s" % (s, ",".join(rs))

        return ["%s=%s" % (k, shared_environment[k]) for k in sorted(shared_environment)]

    def build_compose(self):
        """ build compose file used for docker swarm service """
        node_count = len(self.nodes)
        shared_environment = self.get_shared_environment()

        # static logging referenced by each service
        default_logging = {
            "driver": "json-file",
            "options": {
                "mode": "non-blocking",
                "max-buffer-size": "1m",
                "max-size": ClusterConfig.LOGGING_MAX_SIZE,
                "max-file": ClusterConfig.LOGGING_MAX_FILE,
            },
        }

        config = {"version": "3.3", "services":{}, "networks": {}}
        config["networks"]= {
            "default": {
                "ipam": {
                    "config": [{"subnet":self.app_subnet}]
                }
            }
        }
        config["volumes"] = {
            "web-log":{},
            "redis-log":{},
            "db-log":{},
            "mgr-log":{},
        }

        stdout = "-s" if self.logging_stdout else ""

        # configure webservice (ports are configurable by user)
        web_service = {
            "image": ClusterConfig.APP_IMAGE,
            "command": "/home/app/src/Service/start.sh -r web -l %s" % stdout,
            "ports": [],
            "deploy": {"replicas": 1},
            "logging": copy.deepcopy(default_logging),
            "environment": copy.copy(shared_environment),
            "volumes":[{"web-log":"/home/app/log"}],
        }
        if self.app_http_port > 0:
            web_service["ports"].append("%s:80" % self.app_http_port)
        if self.app_https_port > 0:
            web_service["ports"].append("%s:443" % self.app_https_port)
        config["services"]["web"] = web_service
        self.services["web"] = Service("web")

        # configure redis service (static)
        redis_service = {
            "image": ClusterConfig.APP_IMAGE,
            "command": "/home/app/src/Service/start.sh -r redis -l %s" % stdout,
            "deploy": {"replicas": 1, "endpoint_mode": "dnsrr"},
            "logging": copy.deepcopy(default_logging),
            "environment": copy.copy(shared_environment),
            "volumes":[{"redis-log":"/home/app/log"}],
        }
        config["services"]["redis"] = redis_service
        self.services["redis"] = Service("redis")
        self.services["redis"].set_service_type("redis", port_number=self.redis_port)

        # configure shard service (multiple shards and replicas)
        for s in xrange(0, self.shardsvr_shards):
            for r in xrange(0, self.shardsvr_replicas):
                svc = "db_sh_%s_%s" % (s, r)
                anchor = ((s + r) % node_count) + 1
                env = copy.copy(shared_environment)
                env.append("LOCAL_REPLICA=%s" % r)
                env.append("LOCAL_SHARD=%s" % s)
                env.append("LOCAL_PORT=%s" % self.shardsvr_port)
                env.append("DB_MEMORY=%s" % self.shardsvr_memory)
                env.append("DB_ROLE=shardsvr")
                cmd = "/home/app/src/Service/start.sh -r db -l %s" % stdout
                config["services"][svc] = {
                    "image": ClusterConfig.APP_IMAGE,
                    "command": cmd,
                    "logging": copy.deepcopy(default_logging),
                    "deploy": {
                        "replicas": 1,
                        "endpoint_mode": "dnsrr",
                        "placement": {
                            "constraints": [
                                "node.labels.node == %s" % anchor,
                            ]
                        }
                    },
                    "environment": env,
                    "volumes":[{
                        "%s-log" % svc:"/home/app/log",
                        "%s-data" % svc:"/home/app/local-data",
                    }],
                }

                config["volumes"]["%s-log" % svc] = {}
                config["volumes"]["%s-data" % svc] = {}
                self.services[svc] = Service(svc, node=anchor, replica="sh%s" % s)
                self.services[svc].set_service_type("db_sh", shard_number=s, replica_number=r,
                        port_number=self.shardsvr_port)

        # configure configsvr service (replicas only)
        for r in xrange(0, self.configsvr_replicas):
            svc = "db_cfg_%s" % r
            anchor = (r % node_count) + 1
            cmd = "/home/app/src/Service/start.sh -r db -l %s" % stdout
            env = copy.copy(shared_environment)
            env.append("LOCAL_REPLICA=%s" % r)
            env.append("LOCAL_SHARD=0")
            env.append("LOCAL_PORT=%s" % self.configsvr_port)
            env.append("DB_MEMORY=%s" % self.configsvr_memory)
            env.append("DB_ROLE=configsvr")
            config["services"][svc] = {
                "image": ClusterConfig.APP_IMAGE,
                "command": cmd,
                "logging": copy.deepcopy(default_logging),
                "deploy": {
                    "replicas": 1,
                    "endpoint_mode": "dnsrr",
                    "placement": {
                        "constraints": [
                            "node.labels.node == %s" % anchor
                        ]
                    }
                },
                "environment": env,
                "volumes":[{
                    "%s-log" % svc:"/home/app/log",
                    "%s-data" % svc:"/home/app/local-data",
                }],
            }
            config["volumes"]["%s-log" % svc] = {}
            config["volumes"]["%s-data" % svc] = {}
            self.services[svc] = Service(svc, node=anchor, replica="cfg")
            self.services[svc].set_service_type("db_cfg", replica_number=r, 
                    port_number=self.configsvr_port)

        # configure router (mongos = main db app will use) pointing to cfg replica
        cmd = "/home/app/src/Service/start.sh -r db -l %s" % stdout
        env = copy.copy(shared_environment)
        env.append("LOCAL_REPLICA=0")
        env.append("LOCAL_SHARD=0")
        env.append("LOCAL_PORT=%s" % self.mongos_port)
        env.append("DB_MEMORY=%s" % self.configsvr_memory)
        env.append("DB_ROLE=mongos")
        config["services"]["db"] = {
            "image": ClusterConfig.APP_IMAGE,
            "command": cmd,
            "logging": copy.deepcopy(default_logging),
            "deploy": {
                "mode": "global"        # each node has local db instance
            },
            "environment": env, 
            "volumes":[{"db-log":"/home/app/log"}],
        }
        self.services["db"] = Service("db")
        self.services["db"].set_service_type("db", port_number=self.mongos_port)

        # configure manager, watcher, and workers
        config["services"]["mgr"] = {
            "image": ClusterConfig.APP_IMAGE,
            "command": "/home/app/src/Service/start.sh -r mgr -l -c 1 -i 0 -%s" % stdout,
            "deploy": {"replicas": 1, "endpoint_mode":"dnsrr"},
            "logging": copy.deepcopy(default_logging),
            "environment": copy.copy(shared_environment),
            "volumes":[{"mgr-log":"/home/app/log"}],
        }
        self.services["mgr"] = Service("manager")

        # configure multiple watchers (expect just one or two)
        for i in xrange(0, self.app_watchers):
            svc = "x%s" % i
            config["services"][svc] = {
                "image": ClusterConfig.APP_IMAGE,
                "command": "/home/app/src/Service/start.sh -r watcher -l -c 1 -i %s %s"%(i, stdout),
                "deploy": {"replicas": 1, "endpoint_mode":"dnsrr"},
                "logging": copy.deepcopy(default_logging),
                "environment": copy.copy(shared_environment),
                "volumes":[{"%s-log" % svc:"/home/app/log"}],
            }
            config["volumes"]["%s-log" % svc] = {}
            self.services[svc] = Service(svc)
            self.services[svc].set_service_type("watcher")

        # configure multiple workers
        for i in xrange(0, self.app_workers):
            svc = "w%s" % i
            config["services"][svc] = {
                "image": ClusterConfig.APP_IMAGE,
                "command": "/home/app/src/Service/start.sh -r worker -l -c 1 -i %s %s" % (i,stdout),
                "deploy": {"replicas": 1, "endpoint_mode":"dnsrr"},
                "logging": copy.deepcopy(default_logging),
                "environment": copy.copy(shared_environment),
                "volumes":[{"%s-log" % svc:"/home/app/log"}],
            }
            config["volumes"]["%s-log" % svc] = {}
            self.services[svc] = Service(svc)
            self.services[svc].set_service_type("worker")

        with open(self.compose_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
            logger.info("compose file complete: %s", self.compose_file)

class Service(object):

    SERVICE_TYPES = ["web", "redis", "worker", "manager", "watcher", "db", "db_cfg", "db_sh"]
    def __init__(self, name, node=None, replica=None):
        self.name = name
        self.node = node            # node label_id if constrained to a single node
        self.replica = replica      # name of the replica if part of a replication set
        self.service_type = None
        self.replica_number = None
        self.shard_number = None
        self.port_number = None
        if name in Service.SERVICE_TYPES: 
            self.service_type = name

    def set_service_type(self,service_type,shard_number=None,replica_number=None,port_number=None):
        # set service type (which may be same as the name).  For db_sh, can provided the 
        # shard_number.  The supported services:
        #   web
        #   redis
        #   db      (shard router)
        #   db_cfg  (configserver)
        #   db_sh   (shard)
        #   mgr
        #   watcher
        #   worker
        if service_type not in Service.SERVICE_TYPES:
            raise Exception("unsupported service type %s" % service_type)
        self.service_type = service_type
        if shard_number is not None and service_type == "db_sh":
            self.shard_number = shard_number
        if replica_number is not None and self.replica is not None:
            self.replica_number = replica_number
        if port_number is not None:
            self.port_number = port_number

    def __repr__(self):
        return "name: %s, node: %s, replica-name: %s, type: %s, shard: %s, replica: %s, port: %s" % (
            self.name, self.node, self.replica, self.service_type, self.shard_number,
            self.replica_number, self.port_number)
            

