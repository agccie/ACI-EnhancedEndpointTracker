
from .connection import Connection
from .lib import run_command
from .lib import pretty_print
import getpass
import json
import logging
import re
import time

# module level logging
logger = logging.getLogger(__name__)

class Swarmer(object):

    def __init__(self, config, username=None, password=None):
        # recevies instance of ClusterConfig
        self.config = config
        self.username = username
        self.password = password
        self.nodes = {}
        self.node_id = None         # local node-id
        self.node_addr = None       # local node-addr
        self.node_socket = None     # local node-addr+port for registering worker nodes
        self.token = None           # registration token

        # reindex config.nodes with string id's to match against string labels
        config_nodes = {}
        for nid in self.config.nodes:
            config_nodes["%s" % nid] = self.config.nodes[nid]
        self.config.nodes = config_nodes

    def get_credentials(self):
        # prompt user for username/password if not previously provided
        while self.username is None or len(self.username)==0:
            self.username = raw_input("Enter ssh username: ").strip()
        while self.password is None or len(self.password)==0:
            self.password = getpass.getpass("Enter ssh password: ").strip()

    def get_connection(self, hostname):
        # return ssh connection object to provided hostname, raise exception on error
        
        logger.debug("get connection to %s", hostname)
        self.get_credentials()
        c = Connection(hostname)
        c.username = self.username
        c.password = self.password
        c.protocol = "ssh"
        c.port = 22
        c.prompt = "[#>\$] *$"
        if not c.login(max_attempts=3):
            raise Exception("failed to connect to node %s@%s" % (self.username, hostname))
        return c

    def init_swarm(self):
        # determine the swarm status of this node. If in a swarm but not the manager, raise an error
        # If in a swarm AND the manager, then validate status matches config.
        # If in not in a swarm, then assume this non-initialized system
        js = self.get_swarm_info()
        self.node_id = js["NodeID"]
        self.node_addr = js["NodeAddr"]
        managers = js["RemoteManagers"]
        manager_addr = None
        if len(self.node_id) > 0:
            logger.debug("node %s is part of an existing swarm", self.node_addr)
            self.set_node_socket(managers)
            if self.node_socket is None:
                err_msg = "This node is not a docker swarm manager. "
                err_msg+= "Please execute on the node-1"
                raise Exception(err_msg)
        else:
            # need to initialize this node as a swarm master
            logger.info("initializing swarm master")
            if not run_command("docker swarm init"):
                raise Exception("failed to initialize node as swarm master")
            # get new swarm info
            js = self.get_swarm_info()
            self.node_id = js["NodeID"]
            self.node_addr = js["NodeAddr"]
            managers = js["RemoteManagers"]
            self.set_node_socket(managers)
            if self.node_socket is None:
                raise Exception("failed to init swarm manager, no Addr found in RemoteManagers")

        # validated that swarm is initialized and we're executing on a manager node.  Need to get
        # token for deploying to new workers
        token = run_command("docker swarm join-token worker -q")
        if token is None:
            raise Exception("failed to get swarm token from manager")
        self.token = token.strip()
        logger.debug("swarm token: %s", self.token)

        # get list of current nodes IDs
        self.get_nodes()
        lnode = self.nodes.get(self.node_id, None)
        if lnode is None:
            raise Exception("unable to find local id %s in docker nodes", self.node_id)
        # check label for current node is '1', if not add it
        node_label = lnode.labels.get("node", None)
        if node_label is None:
            logger.debug("adding label '1' to local node")
            cmd = "docker node update --label-add node=1 %s" % self.node_id
            if run_command(cmd) is None:
                raise Exception("failed to add docker node label node=1 to %s" % self.node_id)
            lnode.labels["node"] = "1"
        elif "%s"%node_label != "1":
            err_msg = "This node(%s) has node-id set to %s. Please run on node-1" % (
                    self.node_id, node_label)
            raise Exception(err_msg)
        else:
            logger.debug("node(%s) already assigned with label 1", self.node_id)

        # index nodes by addr and label id, raise error on duplicate
        index_addr = {}
        index_label = {}
        for nid in self.nodes:
            n = self.nodes[nid]
            if n.addr in index_addr:
                raise Exception("duplicate docker node address: %s between %s and %s" % (n.addr,
                    index_addr[n.addr].node_id, nid))
            node_label = n.labels.get("node", None)
            if node_label is None:
                # existing node without a label should not exists, we could try to fix it here but
                # that's a bit out of scope. Will force user to manually fix it for now...
                err_msg = "Node(%s) exists within swarm but does not have a label. " % nid
                err_msg+= "Manually add the appropriate id label via:\n"
                err_msg+= "    docker node update --label-add node=<id> %s" % nid
                raise Exception(err_msg)
            node_label = "%s" % node_label
            if node_label in index_label:
                raise Exception("duplicate docker label node=%s between %s and %s" % (node_label,
                    index_label[node_label].node_id, nid))
            index_addr[n.addr] = n
            index_label[node_label] = n
        logger.debug("index_label: %s", index_label)

        # validate each node in the config or add it if missing
        for node_label in sorted(self.config.nodes):
            # already validate we're on node-id 1, never need to add 1 as worker
            if node_label == "1": continue
            hostname = self.config.nodes[node_label]["hostname"]
            if node_label not in index_label:
                swarm_node_id = self.add_worker(hostname, node_label)
                cmd = "docker node update --label-add node=%s %s" % (node_label, swarm_node_id)
                if run_command(cmd) is None:
                    raise Exception("failed to add docker node label node=%s to %s" % (node_label,
                        swarm_node_id))

        logger.info("docker cluster initialized with %s node(s)", len(self.config.nodes))

    def add_worker(self, hostname, nid):
        """ attempt to connect to remote node and add to docker swarm """
        # prompt user for credentials here if not set...
        logger.info("Adding worker to cluster (id:%s, hostname:%s)", nid, hostname)

        c = self.get_connection(hostname)
        cmd = "docker swarm join --token %s %s" % (self.token, self.node_socket)
        ret = c.cmd(cmd, timeout=60)
        if ret != "prompt":
            raise Exception("failed to add worker(%s) %s: %s" % (nid, hostname, ret))
        if not re.search("This node joined a swarm", c.output):
            raise Exception("failed to add worker(%s) %s: %s" % (nid, hostname, c.output))
        # hopefully node was added, grab the NodeID from the swarm and then make sure it is seen
        # on the master node (over ssh so outputs contain prompt and full command)
        cmd = "docker info --format '{{.Swarm.NodeID}}'"
        ret = c.cmd(cmd)
        if ret != "prompt":
            raise Exception("failed to determine Swarm.NodeID for worker(%s) %s" % (nid, hostname))
        for l in c.output.split("\n"):
            r1 = re.search("^(?P<node_id>[a-zA-Z0-9]{25})$", l.strip())
            if r1 is not None:
                logger.debug("Swarm.NodeID %s for worker(%s) %s", r1.group("node_id"),nid,hostname)
                return r1.group("node_id")
        raise Exception("unable to extract Swarm.NodeID for new worker(%s) %s"% (nid, hostname))

    def set_node_socket(self, managers):
        """ from docker swarm RemoteManagers list, find the socket connection (Addr) for the 
            provided node_id.  Return None on error
        """
        self.node_socket = None
        if managers is not None:
            for m in managers:
                if "NodeID" in m and "Addr" in m and m["NodeID"] == self.node_id:
                    logger.debug("node %s matches manager %s", self.node_id, m)
                    self.node_socket = m["Addr"]
                    return
        logger.debug("node %s not in RemoteManagers list", self.node_id)

    def get_swarm_info(self):
        """ get and validate swarm info from 'docker info' command
            return dict {
                "NodeID": "",
                "NodeAddr": "",
                "RemoteManagers": "",
            }
        """
        # get/validate swarm info from 'docker info' command.  Return 
        info = run_command("docker info --format '{{json .}}'")
        if info is None:
            raise Exception("failed to get docker info, is docker installed?")
        js = json.loads(info)
        logger.debug("local node docker info:%s", pretty_print(js))
        if "Swarm" not in js or "NodeID" not in js["Swarm"] or "NodeAddr" not in js["Swarm"] or \
            "RemoteManagers" not in js["Swarm"]:
            version = js.get("ServerVersion", "n/a")
            raise Exception("no Swarm info, unsupported docker version: %s" % version)
        return {
            "NodeID": js["Swarm"]["NodeID"],
            "NodeAddr": js["Swarm"]["NodeAddr"],
            "RemoteManagers": js["Swarm"]["RemoteManagers"],
        }

    def get_nodes(self):
        """ read docker nodes and update self.nodes """
        logger.debug("get docker node info")
        lines = run_command("docker node ls --format '{{json .}}'")
        if lines is None:
            raise Exception("unable to get docker node info")
        for l in lines.split("\n"):
            if len(l) == 0: continue
            try:
                logger.debug("node: %s", l)
                node = DockerNode(**json.loads(l))
                if node.node_id is not None:
                    self.nodes[node.node_id] = node
                    logger.debug("new node: %s", node)
            except ValueError as e: 
                logger.debug("failed to decode node: '%s'", l)

    def deploy_service(self):
        """ deploy docker service referencing config file and verify everything is running """

        logger.info("deploying app services, please wait...")
        cmd = "docker stack deploy -c %s %s" % (self.config.compose_file, self.config.app_name)
        if run_command(cmd) is None:
            raise Exception("failed to deploy stack")
        
        check_count = 8
        check_interval = 15
        all_services_running = True
        while check_count > 0:
            check_count-= 1
            all_services_running = True
            # check that all the deployed services have at least one replica up 
            cmd = "docker service ls --format '{{json .}}'"
            out = run_command(cmd)
            if out is None:
                raise Exception("failed to validate services are running")
            for l in out.split("\n"):
                if len(l.strip()) == 0: continue
                try:
                    js = json.loads(l)
                    if re.search("^%s_" % re.escape(self.config.app_name), js["Name"]):
                        replicas = re.search("(?P<c>[0-9]+)/(?P<t>[0-9]+)",js["Replicas"])
                        if replicas is not None:
                            if int(replicas.group("c")) < int(replicas.group("t")):
                                err_msg = "failed to deploy service %s (%s/%s)" % (js["Name"],
                                        replicas.group("c"), replicas.group("t"))
                                # if this is last check interation, raise an error
                                if check_count <= 0: raise Exception(err_msg)
                                all_services_running = False
                                logger.debug(err_msg)
                        logger.debug("service %s success: %s", js["Name"], js["Replicas"])
                    else:
                        logger.debug("skipping check for service %s", js["Name"])
                except (ValueError,KeyError) as e:
                    logger.warn("failed to parse docker service line: %s", l)

            if not all_services_running:
                logger.debug("one or more services pending, re-check in %s seconds", check_interval)
                time.sleep(check_interval)
            else: break

        logger.info("app services deployed")
        logger.debug("pausing for 15 seconds to give all services time to actually start")
        time.sleep(15)

    def init_db(self):
        """ need to initialize all replication sets for mongo db based on user config 
            ssh to intended replica primary (replica 0) and initialize replica
        """
        self.init_db_cfg()
        # pause for 15 seconds to ensure that replica set is ready
        logger.debug("pausing for 15 seconds to ensure replica is up")
        time.sleep(15)
        self.init_db_shards()

    def init_db_cfg(self):
        """ initialize cfg server replica set """

        logger.info("initialize db config replica set")
        # find all 'db_cfg' service along with replica '0' info
        rs = {"configsvr": True, "members":[]}
        db_port = None
        replica_0_node = None
        replica_0_name = None
        for svc_name in self.config.services:
            svc = self.config.services[svc_name]
            if svc.service_type == "db_cfg":
                if "_id" not in rs: rs["_id"] = svc.replica
                if svc.replica_number is None or svc.port_number is None:
                    raise Exception("service has invalid replica or port number: %s" % svc)
                host = self.config.nodes.get("%s" % svc.node, None)
                if host is None:
                    raise Exception("failed to determine host for service: %s" % svc)
                member = {
                    "_id": svc.replica_number,
                    "host": "%s:%s" % (svc_name, svc.port_number)
                }
                if svc.replica_number == 0: 
                    replica_0_node = host
                    replica_0_name = svc_name
                    db_port = svc.port_number
                    member["priority"] = 2
                else:
                    member["priority"] = 1
                rs["members"].append(member)

        if replica_0_node is None or replica_0_name is None:
            raise Exception("failed to determine replica 0 db configsrv")

        cmd = 'docker exec -it '
        cmd+= '$(docker ps -qf label=com.docker.swarm.service.name=%s_%s) ' % (
                self.config.app_name, replica_0_name)
        cmd+= 'mongo localhost:%s --eval \'rs.initiate(%s)\'' % (db_port, json.dumps(rs))
        logger.debug("initiate cfg replication set cmd: %s", cmd)
        # cfg server is statically pinned to node-1
        if "%s" % replica_0_node["id"] == "1":
            # hard to parse return json since there's other non-json characters printed so we'll
            # just search for "ok" : 1
            ret = run_command(cmd)
            if ret is None or not re.search("['\"]ok['\"] *: *1 *", ret):
                logger.warn("rs.initiate may not have completed successfully, cmd:%s\nresult:\n%s",
                    cmd, ret)
        else:
            raise Exception("expected cfg server replica 0 to be on node-1, currently on %s" % (
                replica_0_node))

    def init_db_shards(self):
        """ initialize each shard replication set on replica-0 node owner """

        logger.info("initialize db shards")
        # get all service type db_sh and organize into replication sets
        shards = {}     # indexed by shared replica-name, contains node-0 (id and hostname) along
                        # with 'rs' which is initiate dict
        for svc_name in self.config.services:
            svc = self.config.services[svc_name]
            if svc.service_type == "db_sh":
                if svc.replica_number is None or svc.port_number is None:
                    raise Exception("service has invalid replica or port number: %s" % svc)
                if svc.replica not in shards:
                    shards[svc.replica] = {
                        "node-0": None,
                        "svc_name": None,
                        "svc_port": None,
                        "rs": {"_id": svc.replica, "members":[]}
                    }
                host = self.config.nodes.get("%s" % svc.node, None)
                if host is None:
                    raise Exception("failed to determine host for service: %s" % svc)
                member = {
                    "_id": svc.replica_number,
                    "host": "%s:%s" % (svc_name, svc.port_number)
                }
                if svc.replica_number == 0:
                    shards[svc.replica]["node-0"] = host
                    shards[svc.replica]["svc_name"] = svc.name
                    shards[svc.replica]["svc_port"] = svc.port_number
                    member["priority"] = 2
                else:
                    member["priority"] = 1
                shards[svc.replica]["rs"]["members"].append(member)

        for shard_name in shards:
            rs = shards[shard_name]["rs"]
            node_0 = shards[shard_name]["node-0"]
            if node_0 is None:
                raise Exception("failed to find replica 0 node for shard %s" % shard_name)
            cmd = 'docker exec -it '
            cmd+= '$(docker ps -qf label=com.docker.swarm.service.name=%s_%s) ' % (
                    self.config.app_name, shards[shard_name]["svc_name"])
            cmd+= 'mongo localhost:%s --eval \'rs.initiate(%s)\'' % (shards[shard_name]["svc_port"], 
                    json.dumps(rs))
            logger.debug("command on %s: %s", node_0["id"], cmd)
            if "%s" % node_0["id"] == "1":
                # command is executed on local host
                ret = run_command(cmd)
                if ret is None or not re.search("['\"]ok['\"] *: *1 *", ret):
                    err_msg="rs.initiate may not have completed successfully for shard %s"%shard_name
                    err_msg+= ", node (id:%s, hostname:%s)" % (node_0["id"], node_0["hostname"])
                    err_msg+= "\ncmd: %s\nresult: %s" % (cmd, ret)
                    logger.warn(err_msg)
            else:
                c = self.get_connection(node_0["hostname"])
                ret = c.cmd(cmd)
                if ret != "prompt" or not re.search("['\"]ok['\"] *: *1 *", c.output):
                    err_msg="rs.initiate may not have completed successfully for shard %s"%shard_name
                    err_msg+= ", (node id: %s, hostname: %s)" % (node_0["id"], node_0["hostname"])
                    err_msg+= "\ncmd: %s\nresult: %s" % (cmd, "\n".join(c.output.split("\n")[:-1]))
                    logger.warn(err_msg)


        # pause for 15 seconds to ensure that replica set is ready
        logger.debug("pausing for 15 seconds to ensure all replica is up")
        time.sleep(15)

        # add each shard to mongo-router - note, there's an instance of mongos with service name
        # 'db' on all nodes in the cluster so this command is always locally executed
        for shard_name in shards:
            svc_name = shards[shard_name]["svc_name"]
            svc_port = shards[shard_name]["svc_port"]
            cmd = 'docker exec -it '
            cmd+= '$(docker ps -qf label=com.docker.swarm.service.name=%s_db) '%self.config.app_name 
            cmd+= 'mongo localhost:%s --eval \'sh.addShard("%s/%s:%s")\'' % (
                self.config.mongos_port, shard_name, svc_name, svc_port)
            ret = run_command(cmd)
            if ret is None or not re.search("['\"]ok['\"] *: *1 *", ret):
                err_msg="sh.addShard may not have completed successfully for shard %s"%shard_name
                err_msg+= "\ncmd: %s\nresult: %s" % (cmd, ret)
                logger.warn(err_msg)

        
class DockerNode(object):

    def __init__(self, **kwargs):
        self.labels = {}
        self.role = None
        self.addr = None
        self.node_id =  kwargs.get("ID", None)
        self.hostname = kwargs.get("Hostname", None)
        self.availability = kwargs.get("Availability", None)
        self.status = kwargs.get("Status", None)

        if self.node_id is not None:
            inspect = run_command("docker node inspect %s --format '{{json .}}'" % self.node_id)
            if inspect is not None:
                try:
                    logger.debug("inspect: %s", inspect)
                    js = json.loads(inspect)
                    if "Status" in js:
                        if "Addr" in js["Status"]: 
                            self.addr = js["Status"]["Addr"]
                        if "State" in js["Status"]:
                            self.status = js["Status"]["State"]
                    if "Spec" in js:
                        if "Availability" in js["Spec"]:
                            self.availability = js["Spec"]["Availability"]
                        if "Role" in js["Spec"]:
                            self.role = js["Spec"]["Role"]
                        if "Labels" in js["Spec"]:
                            if type(js["Spec"]["Labels"]) is not dict:
                                logger.debug("invalid Labels for %s: %s", self.node_id, js["Spec"])
                            else:
                                self.labels = js["Spec"]["Labels"]
                except ValueError as e:
                    logger.debug("failed to decode inspect(%s): %s", self.node_id, inspect)

    def __repr__(self):
        return "id:%s, role:%s, addr:%s, status:%s, avail:%s, labels:%s" % (
                self.node_id, self.role, self.addr, self.status, self.availability, self.labels
            )
