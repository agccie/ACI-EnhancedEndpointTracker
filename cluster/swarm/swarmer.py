
from .connection import Connection
from .lib import format_timestamp
from .lib import run_command
from .lib import pretty_print
import getpass
import json
import logging
import os
import re
import time
import traceback
import uuid

# module level logging
logger = logging.getLogger(__name__)

class Swarmer(object):
    CERT_EXPIRY = "86400h0m0s"

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
        self.node_hostnames = {}    # indexed by string node value with node hostname (exclude 1)

    def get_credentials(self):
        # prompt user for username/password if not previously provided
        while self.username is None or len(self.username)==0:
            self.username = raw_input("Enter ssh username: ").strip()
        while self.password is None or len(self.password)==0:
            self.password = getpass.getpass("Enter ssh password: ").strip()

    def get_connection(self, hostname, protocol="ssh"):
        # return ssh connection object to provided hostname, raise exception on error
        
        logger.debug("get connection to %s", hostname)
        self.get_credentials()
        c = Connection(hostname)
        c.username = self.username
        c.password = self.password
        c.protocol = protocol
        c.port = 22
        c.prompt = "[#>\$] *$"
        if not c.login(max_attempts=3):
            raise Exception("failed to connect to node %s@%s" % (self.username, hostname))
        return c

    def get_node_hostnames(self):
        # if node_count > 1 then need to prompt user for address/hostname of each node
        if self.config.node_count>0:
            for node_id in xrange(2, self.config.node_count+1):
                # prompt user for hostname/ip address for this node
                node_id = "%s" % node_id
                hostname = self.node_hostnames.get(node_id, "") 
                while hostname is None or len(hostname)==0: 
                    hostname = raw_input("\nEnter hostname/ip address for node %s: "%node_id).strip()
                    if len(hostname) == 0:
                        logger.warn("invalid hostname for node %s, please try again", node_id)
                    elif hostname == self.node_addr:
                        logger.warn("%s is addr of local node, please enter hostname for node %s",
                            hostname, node_id)
                        hostname = ""
                self.node_hostnames[node_id] = hostname

    def init_swarm(self):
        # determine the swarm status of this node. If in a swarm but not the manager, raise an error
        # If in a swarm AND the manager, then validate status matches config.
        # If in not in a swarm, then assume this is non-initialized system
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
            cmd = "docker swarm init --cert-expiry %s" % Swarmer.CERT_EXPIRY
            if not run_command(cmd):
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
        token = run_command("docker swarm join-token manager -q")
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
            self.node_hostnames[node_label] = n.addr
        logger.debug("index_label: %s", index_label)

        # validate each node in the config or add it if missing
        if self.config.node_count>1:
            self.get_node_hostnames()
            for node_label in sorted(self.node_hostnames):
                hostname = self.node_hostnames[node_label]
                if node_label not in index_label:
                    swarm_node_id = self.add_worker(hostname, node_label)
                    cmd = "docker node update --label-add node=%s %s" % (node_label, swarm_node_id)
                    if run_command(cmd) is None:
                        raise Exception("failed to add docker node label node=%s to %s" % (
                            node_label, swarm_node_id))
        logger.info("docker cluster initialized with %s node(s)", self.config.node_count)

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
        # check if stack is already running, if so bail out
        out = run_command("docker stack ls --format '{{json .}}'")
        if out is None:
            raise Exception("failed to deploy stack")
        for l in out.split("\n"):
            if len(l.strip()) == 0: continue
            try:
                js = json.loads(l)
                if "Name" in js and js["Name"] == self.config.app_name:
                    err = "%s stack already running\n" % self.config.app_name
                    err+= "If you want to redeploy the stack, first remove it via "
                    err+= "'docker stack rm %s', wait 5 minutes, " % self.config.app_name
                    err+= "and then rerun this script."
                    raise Exception(err)
            except (ValueError,KeyError) as e:
                logger.warn("failed to parse docker service line: %s", l)

        cmd = "docker stack deploy -c %s %s" % (self.config.compose_file, self.config.app_name)
        if run_command(cmd) is None:
            raise Exception("failed to deploy stack")
        
        check_count = 15
        check_interval = 60.0
        all_services_running = True
        while check_count > 0:
            check_count-= 1
            pending_services = 0
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
                                pending_services+= 1
                                logger.debug(err_msg)
                        logger.debug("service %s success: %s", js["Name"], js["Replicas"])
                    else:
                        logger.debug("skipping check for service %s", js["Name"])
                except (ValueError,KeyError) as e:
                    logger.warn("failed to parse docker service line: %s", l)

            if not all_services_running:
                logger.info("%s services pending, re-check in %s seconds", pending_services, 
                            check_interval)
                time.sleep(check_interval)
            else: break

        logger.info("app services deployed")
        logger.debug("pausing for 15 seconds to give all services time to actually start")
        time.sleep(15)

    def collect_techsupport(self, name="tsod", path="/tmp/", logfile=None):
        """ collect techsupport (collection of logs) from all nodes in the cluster and save to 
            provided path. This requires the following steps:
                - get list of active nodes in the cluster
                - for each node, execute list of commands and bundle into file
                - scp all files over to local node and place into path directory
            return boolean success
        """
        js = self.get_swarm_info()
        self.node_id = js["NodeID"]
        self.node_addr = js["NodeAddr"]
        if len(self.node_id) == 0:
            err = "This node is not part of a swarm, please initialize swarm before collecting "
            err+= "a techsupport."
            logger.error(err)
            return False

        # tmp techsupport name
        ts = "%s-%s" % (name, format_timestamp(time.time()))
        # get active nodes in the cluster
        self.get_nodes()
        if len(self.nodes) > 0:
            logger.info("collecting techsupport %s from %s nodes", ts, len(self.nodes))
            # need ssh credentials to access other nodes before continuing...
            self.get_credentials()
        else:
            logger.info("collecting techsupport %s from local node", ts)

        # make result folder to store techsupport data
        final_path = os.path.abspath("%s/%s" % (path, ts))
        os.makedirs(final_path)

        otmp = "/tmp/%s" % uuid.uuid4()
        # collect techsupport from each node
        for node_id in sorted(self.nodes, key=lambda node_id: self.nodes[node_id].addr):
            node = self.nodes[node_id]
            label = "node-%s" % node.labels.get("node", node.node_id)
            logger.info("collecting techsupport data from %s (%s)", label, node.addr)
            # tmp directory for data collection
            c = None
            scp = Connection("scp")
            try:
                tmp = "%s/%s" % (otmp, label)
                # connection is either ssh connection or just local bash shell.
                if node.node_id == self.node_id:
                    c = self.get_connection("localhost", protocol="bash")
                else:
                    c = self.get_connection(node.addr)
                # make a temporary directory for this ts and collect all commands
                logger.debug("creating temporary directory for data collection: %s", tmp)
                c.cmd("mkdir -p %s" % tmp)
                commands = [
                    "mkdir -p %s" % tmp,
                    "cp /var/log/* %s/" % tmp,
                    "dmesg > %s/dmesg.log" % tmp,
                    "df -h > %s/df_h.log" % tmp,
                    "journalctl -u docker.service > %s/docker.journalctl.log" % tmp,
                    "docker system info > %s/docker_system.log" % tmp,
                    "docker system df >> %s/docker_system.log" % tmp,
                    "docker node ls >> %s/docker_system.log" % tmp,
                    "docker system events --since 2019-01-01 --until `date +\"%%Y-%%m-%%dT%%H:%%M:%%S\"` >> %s/docker_system.log" % tmp,
                    "docker stats --no-stream --no-trunc > %s/docker_stats.log" % tmp,
                    "docker ps --no-trunc > %s/docker_ps.log" % tmp,
                    "docker service ls > %s/docker_service.log" % tmp,
                    "docker service inspect $(docker service ls -q) >> %s/docker_service.log" % tmp,
                    "docker inspect $(docker ps -q) > %s/docker_container_inspect.log" % tmp,
                    "docker volume inspect $(docker volume ls -q) > %s/docker_volume_inspect.log" % tmp,
                    # bash script to collect the logs from all containers running on this host
                    "services=$(docker service ls --format {{.Name}})",
                    "for svc in $services ; do ",
                    "docker service ps $svc > %s/docker_service_$svc.log" % tmp,
                    "docker service logs $svc >> %s/docker_service_$svc.log" % tmp,
                    "done",
                    "IFS=$'\\n'",
                    "containers=$(docker ps --format '{{.ID}} {{.Names}}')",
                    "for x in $containers ; do",
	            "IFS=' ' read -r -a _x1 <<< \"$x\"",
	            "IFS='.' read -r -a _x2 <<< \"${_x1[1]}\"",
	            'cid=${_x1[0]}',
	            'name=${_x2[0]}',
                    'docker exec -it $cid bash -c "mkdir -p /tmp/$name ; cp -rf /home/app/log/* /tmp/$name/ ; cd /tmp/ ; tar -zcvf /tmp/local.tgz $name "',
	            'docker cp $cid:/tmp/local.tgz %s/$name.tgz' % tmp,
                    'docker exec -it $cid bash -c "rm -rf /tmp/$name "',
                    "IFS=$'\\n'",
                    'done',
                    # compress all the files in tmp to single file
                    "cd %s ; tar -zcvf %s.tgz ./* ; mv %s.tgz /tmp/" % (otmp, label, label),
                ]
                for command in commands:
                    logger.debug("executing collection command: %s", command)
                    ret = c.cmd(command)
                    if ret != "prompt":
                        logger.warn("command failed with ret %s", ret)
                        # quit on error
                        break

                # try to scp collected files
                if node.node_id == self.node_id:
                    c.cmd("mv /tmp/%s.tgz %s/" % (label, final_path))
                else:
                    # need to scp the file from the home directory and then (on success) remove it
                    _scp = "scp %s@%s:/tmp/%s.tgz %s/" % (c.username, c.hostname, label, final_path)
                    logger.debug("copy file: %s", _scp)
                    scp.username = c.username
                    scp.password = c.password
                    scp.protocol = _scp
                    scp.prompt = "[#>\$] *$"
                    scp.login(max_attempts=3, timeout=180)
                    # check if copy was successful
                    if not os.path.exists("%s/%s.tgz" % (final_path, label)):
                        logger.error("failed to copy %s.tgz", label)

            except Exception as e:
                logger.error("failed to collect data from %s", node)
                logger.debug("Traceback:\n%s", traceback.format_exc())
            finally:
                # try to clean up tmp directory
                if c is not None:
                    logger.debug("attempting to cleanup tmp directory %s", otmp)
                    c.cmd("rm -rfv %s" % otmp, timeout=10)
                    c.close()
                if scp is not None:
                    scp.close()

        # bundle final results in final_path into single file
        logger.info("bundling final results")
        if logfile is not None:
            run_command("cp %s %s/" % (logfile, final_path))
        run_command("cd %s/../ ; tar -zcvf %s.tgz %s/* ; mv %s.tgz /tmp/ ; rm -rfv %s" % (
                    final_path, ts, ts, ts, final_path), ignore=True)
        logger.info("techsupport location: /tmp/%s.tgz" % ts)

    def wipe(self):
        """ remove current stack deployment and then clean up all volumes and stopped containers """
        # to cleanup we will need ssh credentials if node count > 0 
        self.get_nodes()
        if len(self.nodes) > 0:
            self.get_credentials()
        # validate credentials  by creating ssh connection to each node and saving to node object
        for node_id in self.nodes:
            node = self.nodes[node_id]
            if node.node_id == self.node_id:
                node.connection = self.get_connection("localhost", protocol="bash")
            else:
                node.connection = self.get_connection(node.addr)

        logger.info("removing stack %s", self.config.app_name)
        run_command("docker stack rm %s" % self.config.app_name)
        # command should block until it completes but we will give it 30 extra seconds
        sleep=30
        logger.debug("waiting %s seconds for services to go down", sleep)
        time.sleep(sleep)
        # remove all containers and all volumes from each node
        for node_id in sorted(self.nodes, key=lambda node_id: self.nodes[node_id].addr):
            node = self.nodes[node_id]
            logger.debug("removing containers from %s", node)
            node.connection.cmd("docker rm $(docker ps -aq)", ignore=True)
            logger.debug("removing volumes from %s", node)
            node.connection.cmd("docker volume rm $(docker volume ls -q)", ignore=True)
        logger.info("cleanup complete")

        
class DockerNode(object):

    def __init__(self, **kwargs):
        self.labels = {}
        self.role = None
        self.addr = None
        self.connection = None
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
