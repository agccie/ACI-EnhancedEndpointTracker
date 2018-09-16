
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
        while self.username is None or len(self.username)==0:
            self.username = raw_input("Enter ssh username: ").strip()
        while self.password is None or len(self.password)==0:
            self.password = getpass.getpass("Enter ssh password: ").strip()

        c = Connection(hostname)
        c.username = self.username
        c.password = self.password
        c.protocol = "ssh"
        c.port = 22
        c.prompt = "[#>\$] *$"
        if not c.login(max_attempts=3):
            raise Exception("failed to connect to node(%s) %s@%s"%(nid, self.username, hostname))
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
