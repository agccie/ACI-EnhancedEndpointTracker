import copy
import logging
import re
import yaml

logger = logging.getLogger(__name__)

class ClusterConfig(object):
    """ manage parsing user config.yml to swarm compose file """

    APP_IMAGE = "aci/enhancedendpointtracker:2.0"
    MONGO_IMAGE = "mongo:3.6.7"
    REDIS_IMAGE = "redis:4.0.11"

    # limits to prevent accidental overprovisioning
    MAX_NODES = 10
    MAX_WORKERS = 128
    MIN_PREFIX = 8
    MAX_PREFIX = 27
    MAX_SHARDS = 32
    MAX_REPLICAS = 3
    MAX_MEMORY = 512

    # everything has the same logging limits for now
    LOGGING_MAX_SIZE = "50m"
    LOGGING_MAX_FILE = "10"

    def __init__(self):
        self.nodes = {}         # indexed by node id, {"id":int, "hostname":"addr"}
        self.app_workers = 5
        self.app_subnet = "192.0.2.0/27"
        self.app_name = "ept"
        # set http/https port to 0 to disable that service
        self.app_http_port = 80
        self.app_https_port = 443
        self.shardsvr_shards = 1
        self.shardsvr_memory = 2.0
        self.shardsvr_replicas = 1
        self.shardsvr_port = 27107
        self.configsvr_memory = 2.0
        self.configsvr_replicas = 1
        self.configsvr_port = 27019
        self.mongos_port = 27017
        self.compose_file = "./compose.yml"

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

    def build_compose(self):
        """ build compose file used for docker swarm service """
        node_count = len(self.nodes)

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

        config = {"version": "3", "services":{}, "networks": {}}
        config["networks"]= {
            "default": {
                "ipam": {
                    "config": [{"subnet":self.app_subnet}]
                }
            }
        }
        # configure webservice (ports are configurable by user)
        web_service = {
            "image": ClusterConfig.APP_IMAGE,
            "command": "/bin/sleep infinity",
            "ports": [],
            "deploy": {"replicas": 1},
            "logging": copy.deepcopy(default_logging),
        }
        if self.app_http_port > 0:
            web_service["ports"].append("%s:80" % self.app_http_port)
        if self.app_https_port > 0:
            web_service["ports"].append("%s:443" % self.app_https_port)
        config["services"]["web"] = web_service

        # configure redis service (static)
        redis_service = {
            "image": ClusterConfig.REDIS_IMAGE,
            "logging": copy.deepcopy(default_logging),
        }
        config["services"]["redis"] = redis_service

        # configure shard service (multiple shards and replicas)
        for s in xrange(0, node_count*self.shardsvr_shards):
            for r in xrange(0, self.shardsvr_replicas):
                svc = "db_sh_%s_%s" % (s, r)
                anchor = ((s + r) % node_count) + 1
                cmd = "mongod --shardsvr --replSet sh%s " % s
                cmd+= "--wiredTigerCacheSizeGB %s " % self.shardsvr_memory
                cmd+= "--bind_ip_all --port %s " % self.shardsvr_port 
                config["services"][svc] = {
                    "image": ClusterConfig.MONGO_IMAGE,
                    "command": cmd,
                    "logging": copy.deepcopy(default_logging),
                    "deploy": {
                        "replicas": 1,
                        "placement": {
                            "constraints": [
                                "node.labels.node == %s" % anchor,
                            ]
                        }
                    },
                }

        # configure configsvr service (replicas only)
        cfg_str = "cfg/"
        for r in xrange(0, self.configsvr_replicas):
            svc = "db_cfg_%s" % r
            anchor = (r % node_count) + 1
            cfg_str+= "%s:%s," % (svc, self.configsvr_port)
            cmd = "mongod --configsvr --replSet cfg "
            cmd+= "--wiredTigerCacheSizeGB %s " % self.configsvr_memory
            cmd+= "--bind_ip_all --port %s " % self.configsvr_port 
            config["services"][svc] = {
                "image": ClusterConfig.MONGO_IMAGE,
                "command": cmd,
                "logging": copy.deepcopy(default_logging),
                "deploy": {
                    "replicas": 1,
                    "placement": {
                        "constraints": [
                            "node.labels.node == %s" % anchor
                        ]
                    }
                },
            }
        cfg_str = re.sub(",$","", cfg_str)

        # configure router (mongos = main db app will use) pointing to cfg replica
        cmd = "mongos --configdb %s --bind_ip_all --port %s" % (cfg_str, self.mongos_port)
        config["services"]["db"] = {
            "image": ClusterConfig.MONGO_IMAGE,
            "command": cmd,
            "logging": copy.deepcopy(default_logging),
        }

        # configure workers
        cmd = "/bin/sleep infinity"
        for i in xrange(0, self.app_workers):
            svc = "w%s" % i
            config["services"][svc] = {
                "image": ClusterConfig.APP_IMAGE,
                "command": cmd,
                "logging": copy.deepcopy(default_logging),
            }

        with open(self.compose_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

