
import copy
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
            if len(self.containers) == 0:
                raise Exception("no valid database containers defined")

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
            "WEB_PORT": self.https_port,
            "REDIS_PORT": self.redis_port,
            "REDIS_HOST": self.service_name.format(self.redis_name),
            "DB_MEMORY": self.db_memory,
            "DB_SHARD_COUNT": self.shards,
            "DB_REPLICA_COUNT": len(self.containers),
            "MONGO_HOST": self.service_name.format("%s-mongos" % self.containers[0]["name"]),
            "MONGO_PORT": self.containers[0]["base_port"],
        }
        cfg_srvs = []
        shard_rs = {}   # shard replica sets indexed by shard number
        for i, c in enumerate(self.containers):
            shared_environment["DB_PORT_%s" % c["name"]] = c["base_port"]
            cfg = "%s:%s" % (self.service_name.format("%s-cfg" % c["name"]), c["base_port"]+1)
            cfg_srvs.append(cfg)
            for s in xrange(0, self.shards):
                shard_hostname = "%s:%s" % (
                    self.service_name.format("%s-sh%s" % (c["name"], s)),
                    c["base_port"] + s + 2
                )
                if s not in shard_rs: shard_rs[s] = []
                shard_rs[s].append(shard_hostname)
        shared_environment["DB_CFG_SRV"] = "cfg/%s" % (",".join(cfg_srvs))
        # add each shard replica set environment variable
        for sh in sorted(shard_rs):
            shared_environment["DB_RS_SHARD_%s" % sh] = "sh%s/%s" % (sh, ",".join(shard_rs[sh]))


        # ensure all environment variables are casted to strings
        for a in shared_environment:
            shared_environment[a] = "%s" % shared_environment[a]

        def get_generic_service(srv_name,srv_args=[],memory=None,cpu=None,ports={},services=[],
            service_type="service", environment={}, group=None, container_only=False):
            # build a generic service to add to config["jobs"]
            resources = {}
            env = copy.copy(shared_environment)
            for a in environment:
                env[a] = "%s" % environment[a]
            if memory is not None:
                resources["MemoryLabel"] = memory
            if cpu is not None:
                resources["CPULabel"] = cpu
            if group is None:
                group = "group-%s" % srv_name
            ret = {
                "type": service_type,
                "meta": {
                    "tag": srv_name
                },
                "groups": {
                    group: {
                        "containers": {
                             srv_name: {
                                "image": KronConfig.APP_IMAGE,
                                "command": "/home/app/src/Service/start.sh",
                                "args": srv_args,
                                "environment": env,
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
            if container_only: 
                return ret["groups"][group]["containers"][srv_name]
            else:
                return ret

        # add required apiserver-service (web) first
        web_name = "%s_web" % self.short_name
        config["jobs"]["service-%s" % web_name] = get_generic_service(
            web_name, 
            service_type="system",
            srv_args=["-r","web"], 
            ports={"apiserver-port": self.https_port},
            services=[{"name":"apiserver-service", "port":"apiserver-port"}]
        )
        # add redis service, manager, and db1 all to the same taskgroup group service-primary to 
        # pin to same node
        group = "group-primary"
        redis_name = "%s_redis" % self.short_name
        config["jobs"]["service-primary"] = get_generic_service(
            redis_name, 
            srv_args=["-r","redis"], 
            ports={"redis-port": self.redis_port},
            services=[{"name":self.redis_name, "port":"redis-port"}],
            group=group
        )
        primary_containers = config["jobs"]["service-primary"]["groups"][group]["containers"]
        # add manager services (includes workers)
        mgr_name = "%s_mgr" % self.short_name
        primary_containers[mgr_name] = get_generic_service(
            mgr_name,
            srv_args=["-r", "mgr"],
            memory="large",
            cpu="ludicrous",
            container_only=True,
        )
        # add each db container
        for r, c in enumerate(self.containers):
            srv_name = "%s_%s" % (self.short_name, c["name"])
            ports = {"mongos": c["base_port"], "cfg": c["base_port"]+1}
            services = [
                {"name":"%s-mongos" % c["name"], "port":"mongos"},
                {"name":"%s-cfg" % c["name"], "port":"cfg"},
            ]
            for s in xrange(0, self.shards):
                ports["sh%s" % s] = c["base_port"] + s + 2
                services.append({"name":"%s-sh%s" % (c["name"], s), "port": "sh%s" % s})
            group = "service-primary"
            if r > 0:
                config["jobs"]["service-rep-%s" % r] = get_generic_service(
                    srv_name,
                    srv_args=["-r", "db"],
                    cpu="ludicrous",
                    memory="jumbo",
                    ports=ports,
                    services=services,
                    environment={"LOCAL_REPLICA": c["name"]},
                )
            else:
                primary_containers[srv_name] = get_generic_service(
                    srv_name,
                    srv_args=["-r", "db"],
                    cpu="ludicrous",
                    memory="jumbo",
                    ports=ports,
                    services=services,
                    environment={"LOCAL_REPLICA": c["name"]},
                    container_only=True
                )

        return config

if __name__ == "__main__":

    default_config = "%s/kron_config.yml" % os.path.dirname(os.path.realpath(__file__))
    k = KronConfig(default_config)
    print json.dumps(k.build_cluster_config(), indent=4, separators=(",", ":"), sort_keys=True)
