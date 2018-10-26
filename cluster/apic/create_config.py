import logging
import json
import os
import yaml

logger = logging.getLogger(__name__)

class KronConfig(object):
    """ manage parsing user kron_config.yml to create clusterMgrConfig file """

    APP_IMAGE = "aci/enhancedendpointtracker:2.0"

    def __init__(self, configfile):
        self.name = "EnhancedEndpointTracker"
        self.short_name = "ept"
        self.service_name = {}
        self.https_name = "apiserver-service"
        self.https_port = 8443
        self.redis_name = "redis"
        self.redis_port = 6379
        self.workers = 6
        self.shards = 3
        self.db_memory = 2
        self.containers = []
        self.db_cfg_replica_set = "cfg"
        self.db_sh_replica_set = "sh"
        
        # import config
        self.import_config(configfile)

    def import_config(self, configfile):
        """ import/parse and validate config file, raise exception on error """
        logger.info("loading config file: %s", configfile)
        with open(configfile, "r") as f:
            try:
                config = yaml.load(f)
            except yaml.parser.ParserError as e:
                logger.debug(e)
                raise Exception("failed to parse config file")
            # relax checks here, just try and import what we expect
            for a in ["name", "short_name", "https_port", "redis_name", "redis_port", "workers"]:
                if a in config:
                    setattr(self, a, config[a])
            # force name and short_name to all lower case and set service_name
            self.name = self.name.lower()
            self.short_name = self.short_name.lower()
            self.service_name = "{}-cisco-%s.service.apic.local" % self.name

            if "database" in config:
                if "memory" in config["database"]:
                    self.db_memory = config["database"]["memory"]
                if "shards" in config["database"]:
                    self.shards = config["database"]["shards"]
                if "containers" in config["database"] and \
                    type(config["database"]["containers"]) is list:
                    for c in config["database"]["containers"]:
                        if "name" in c and "base_port" in c:
                            self.containers.append({
                                "name": c["name"],
                                "base_port": c["base_port"],
                            })

    def build_cluster_config(self):
        """ build kron cluster configfile """
        config = {
            "name": self.name,
            "jobs": {}
        }
        default_restart = {
            "attempts": 10,
            "delay": "25s",
            "interval": "5m",
            "mode": "delay"
        }
        shared_environment = {
            "HOSTED_PLATFORM": "APIC",
            "REDIS_PORT": self.redis_port,
            "REDIS_HOST": self.service_name.format(self.redis_name),
            "DB_MEMORY": self.db_memory,
            "DB_SHARD_COUNT": self.shards,
            "DB_REPLICA_COUNT": len(self.containers),
            "DB_CFG_REPLICA_SET": self.db_cfg_replica_set,
        }
        self.db_cfg_replica_set = "cfg"
        self.db_sh_replica_set = "sh"
        cfg_srvs = []
        for i, c in enumerate(self.containers):
            hostname = "%s:%s" % (self.service_name.format("%s_cfg" % c["name"]), c["base_port"])
            cfg_srvs.append(hostname)
            shared_environment["DB_CFG_REPLICA_%s" % i] =  hostname
            for s in xrange(0, self.shards):
                shared_hostname = "%s:%s" % (
                    self.service_name.format("%s_sh%s" % (c["name"], s)),
                    c["base_port"] + s + 1
                )
                shared_environment["DB_SHARD_%s_REPLICA_%s" % (s, i)] = shared_hostname
        shared_environment["DB_CFG_SRV"] = "%s/%s" % (self.db_cfg_replica_set, ",".join(cfg_srvs))

        def get_generic_service(srv_name,srv_args=[],memory=None,cpu=None,ports={},services=[]):
            # build a generic service to add to config["jobs"]
            resources = {}
            if memory is not None:
                resources["MemoryLabel"] = memory
            if cpu is not None:
                resources["CPULabel"] = cpu
            return {
                "type": "service",
                "meta": {
                    "tag": srv_name
                },
                "groups": {
                    "group-%s" % srv_name: {
                        "containers": {
                             srv_name: {
                                "image": KronConfig.APP_IMAGE,
                                "command": "/home/app/src/service/start.sh",
                                "args": srv_args,
                                "environment": shared_environment,
                            "meta": resources,
                            "ports": ports,
                            "services": services,
                            },
                        },
                        "count": 1,
                        "restart": default_restart
                    },
                },
            }

        # add required apiserver-service (web) first
        web_name = "%s_web" % self.short_name
        config["jobs"]["service-%s" % web_name] = get_generic_service(
            web_name, 
            srv_args=["-r","web"], 
            ports={"apiserver-port": self.https_port},
            services=[{"name":"apiserver-service", "port":"apiserver-port"}]
        )
        # add redis service
        redis_name = "%s_redis" % self.short_name
        config["jobs"]["service-%s" % redis_name] = get_generic_service(
            redis_name, 
            srv_args=["-r","redis"], 
            ports={"redis-port": self.redis_port},
            services=[{"name":self.redis_name, "port":"redis-port"}]
        )
        # add manager services (includes workers)
        mgr_name = "%s_mgr" % self.short_name
        config["jobs"]["service-%s" % mgr_name] = get_generic_service(
            mgr_name,
            srv_args=["-r", "mgr"],
            cpu="ludicrous"
        )
        # add each db container
        for c in self.containers:
            srv_name = "%s_%s" % (self.short_name, c["name"])
            ports = {"cfg": c["base_port"]}
            services = [{"name":"%s_cfg" % c["name"], "port":"cfg"}]
            for s in xrange(0, self.shards):
                ports["sh%s" % s] = c["base_port"] + s + 1
                services.append({"name":"%s_sh%s" % (c["name"], s), "port": "sh%s" % s})
            config["jobs"]["service-%s" % srv_name] = get_generic_service(
                srv_name,
                srv_args=["-r", "db"],
                cpu="ludicrous",
                memory="jumbo",
                ports=ports,
                services=services
            )

        return config

if __name__ == "__main__":

    default_config = "%s/kron_config.yml" % os.path.dirname(os.path.realpath(__file__))
    k = KronConfig(default_config)
    print json.dumps(k.build_cluster_config(), indent=4, separators=(",", ":"), sort_keys=True)
