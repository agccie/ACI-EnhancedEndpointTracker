
from ... utils import get_db
from ... utils import get_redis

from .. utils import get_apic_session
from .. utils import get_attributes
from .. utils import get_class
from .. utils import get_controller_version
from .. utils import parse_apic_version
from .. utils import pretty_print
from .. subscription_ctrl import SubscriptionCtrl

from . common import MANAGER_CTRL_CHANNEL
from . common import MANAGER_WORK_QUEUE
from . common import MINIMUM_SUPPORTED_VERSION
from . common import get_vpc_domain_id
from . ept_msg import MSG_TYPE
from . ept_msg import WORK_TYPE
from . ept_msg import eptMsg
from . ept_msg import eptMsgWork
from . ept_epg import eptEpg
from . ept_history import eptHistory
from . ept_node import eptNode
from . ept_tunnel import eptTunnel
from . ept_settings import eptSettings
from . ept_subnet import eptSubnet
from . ept_vnid import eptVnid
from . ept_vns_rs_lif_ctx_to_bd import eptVnsRsLIfCtxToBD
from . ept_vpc import eptVpc

from importlib import import_module

import logging
import re
import threading
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

mo_map = {
    "fvCtx": {
        "object": "eptVnid",
        "db": {
            "name": "dn",
            "vnid": "scope",
            "vrf": "scope",
            "pctag": "pcTag",
        },
    },
    "fvBD": {
        "object": "eptVnid",
        "db": {
            "name": "dn",
            "vnid": "seg",
            "vrf": "vnid",
            "pctag": "pcTag",
        },
    },
    "fvSvcBD": {
        "object": "eptVnid",
        "db": {
            "name": "dn",
            "vnid": "seg",
            "vrf": "vnid",
            "pctag": "pcTag",
        },
    },
    "l3extExtEncapAllocator": {
        "object": "eptVnid",
        "db": {
            "name": "dn",
            "encap": "encap",
            "vnid": "extEncap",
            "vrf": "fvCtx.scope",
        },
        "regex_map": {
            "vnid": "vxlan-(?P<value>[0-9]+)",
        },
    },
}

class eptSubscriber(object):
    def __init__(self, fabric):
        # receive instance of Fabric rest object
        self.fabric = fabric
        self.settings = eptSettings.load(fabric=self.fabric.fabric)
        self.initializing = True    # set to queue events until fully initialized
        self.stopped = False        # set to ignore events after hard_restart triggered
        self.db = None
        self.redis = None
        self.session = None
        self.soft_restart_ts = 0    # timestamp of last soft_restart
        self.vpc_rebuild_ts = 0     # timestamp of last eptVpc rebuild
        self.manager_ctrl_channel_lock = threading.Lock()
        self.manager_work_queue_lock = threading.Lock()
        self.subscription_check_interval = 5.0   # interval to check subscription health

        # list of pending events received on subscription while in init state
        self.pending_events = []        
        # statically defined classnames in which to subscribe
        # slow subscriptions are classes which we expect a low number of events
        subscription_classes = [
            "fabricProtPol",        # handle_fabric_prot_pol
            "fabricAutoGEp",        # handle_fabric_group_ep
            "fabricExplicitGEp",    # handle_fabric_group_ep
            "fabricNode",           # handle_fabric_node
            "vpcRsVpcConf",         # handle_rs_vpc_conf_event
            #"fvCtx",                # handle_vnid_event
            #"fvBD",                 # handle_vnid_event
            #"fvSvcBD",              # handle_vnid_event
            #"fvEPg",                # this includes fvAEPg, l3extInstP, vnsEPpInfo
            #"fvRsBd",
            #"vnsRsEPpInfoToBD",
            #"vnsRsLIfCtxToBD",      
            #"l3extExtEncapAllocator",
            #"fvSubnet",             # handle_subnet_event
            #"fvIpAttr",             # handle_subnet_event
        ]
        # classname to function handler for subscription events
        self.handlers = {                
            "fabricProtPol": self.handle_fabric_prot_pol,
            "fabricAutoGEp": self.handle_fabric_group_ep,
            "fabricExplicitGEp": self.handle_fabric_group_ep,
            "fabricNode": self.handle_fabric_node,
            "vpcRsVpcConf": self.handle_rs_vpc_conf_event,
            #"fvSubnet": self.handle_subnet_event,
            #"fvIpAttr": self.handle_subnet_event,
            #"fvCtx": self.handle_vnid_event,
            #"fvBD": self.handle_vnid_event,
            #"fvSvcBD": self.handle_vnid_event,
        }

        # epm subscriptions expect a high volume of events
        epm_subscription_classes = [
            "epmMacEp",
            "epmIpEp",
            "epmRsMacEpToIpEpAtt",
        ]

        self.mo_classes = [
            "fvCtx",
            "fvBD",
            "fvSvcBD",
            "l3extExtEncapAllocator",
            "l3extInstP",
            "l3extOut",
            "l3extRsEctx",
            "fvAEPg",
            "fvRsBd",
            "vnsEPpInfo",
            "vnsRsEPpInfoToBD",
            "mgmtInB",
            "mgmtRsMgmtBD",
            "fvSubnet",
            "fvIpAttr",
            "vnsLIfCtx",
            "vnsRsLIfCtxToBD",
        ]
        # create subscription object for slow and fast subscriptions
        slow_interest = {}
        epm_interest = {}

        for s in subscription_classes:
            slow_interest[s] = {"handler": self.handle_event}
        for mo in self.mo_classes:
            slow_interest[s] = {"handler": self.handle_std_mo_event}
        for s in epm_subscription_classes:
            epm_interest[s] = {"handler": self.handle_event}

        self.slow_subscription = SubscriptionCtrl(
            self.fabric, 
            slow_interest, 
            heartbeat=300,
            inactive_interval=1
        )
        self.epm_subscription = SubscriptionCtrl(
            self.fabric, 
            epm_interest, 
            heartbeat=300,
            inactive_interval=0.01
        )

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        logger.info("starting eptSubscriber for fabric '%s'", self.fabric.fabric)
        try:
            # allocate a unique db connection as this is running in a new process
            self.db = get_db(uniq=True, overwrite_global=True)
            self.redis = get_redis()
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        finally:
            self.slow_subscription.unsubscribe()
            self.epm_subscription.unsubscribe()

    def _run(self):
        """ monitor fabric and enqueue work to workers """

        init_str = "initializing"
        # first step is to get a valid apic session, bail out if unable to connect
        self.fabric.add_fabric_event(init_str, "connecting to apic")
        self.session = get_apic_session(self.fabric)
        if self.session is None:
            logger.warn("failed to connect to fabric: %s", self.fabric.fabric)
            self.fabric.add_fabric_event("failed", "failed to connect to apic")
            return

        # get controller version, highlight mismatch and verify minimum version
        apic_version = get_controller_version(self.session)
        if len(apic_version) == 0:
            logger.warn("failed to determine apic version")
            self.fabric.add_fabric_event("failed", "failed to determine apic version")
            return
        apic_version_set = set([n["version"] for n in apic_version])
        if len(apic_version_set)>1:
            logger.warn("version mismatch for %s: %s", self.fabric.fabric, apic_version_set)
            self.fabric.add_fabric_event("warning", "version mismatch: %s" % ", ".join([
                    "apic-%s: %s" % (n["node"], n["version"]) for n in apic_version
                ]))
        # use whatever the first detected version is for validation, we don't expect version 
        # mismatch for controllers so warning is sufficient
        min_version = parse_apic_version(MINIMUM_SUPPORTED_VERSION)
        version = parse_apic_version(apic_version[0]["version"])
        self.fabric.add_fabric_event(init_str, "apic version: %s" % apic_version[0]["version"])
        if version is None or min_version is None:
            logger.warn("failed to parse apic version: %s (min version: %s)", version, min_version)
            self.fabric.add_fabric_event("failed","unknown or unsupported apic version: %s" % (
                apic_version[0]["version"]))
            self.fabric.auto_start = False
            self.fabric.save()
            return
        # will check major/min/build and ignore patch for version check for now
        min_matched = True
        if version["major"] < min_version["major"]:
            min_matched = False
        elif version["major"] == min_version["major"]:
            if version["minor"] < min_version["minor"]:
                min_matched = False
            elif version["minor"] == min_version["minor"]:
                min_matched = (version["build"] >= min_version["build"])
        if not min_matched:
            logger.warn("fabric does not meet minimum code version (%s < %s)", version, min_version)
            self.fabric.add_fabric_event("failed","unknown or unsupported apic version: %s" % (
                apic_version[0]["version"]))
            self.fabric.auto_start = False
            self.fabric.save()
            return

        # get overlay vnid and fabricProtP (which requires hard reset on change)
        vpc_attr = get_attributes(session=self.session, dn="uni/fabric/protpol")
        overlay_attr = get_attributes(session=self.session, dn="uni/tn-infra/ctx-overlay-1")
        if overlay_attr and "scope" in overlay_attr:
            self.settings.overlay_vnid = int(overlay_attr["scope"])
            if vpc_attr and "pairT" in vpc_attr:
                self.settings.vpc_pair_type = vpc_attr["pairT"]
                self.settings.save()
            else:
                logger.warn("failed to determine fabricProtPol pairT: %s (using default)",vpc_attr)
        else:
            logger.warn("failed to determine overlay vnid: %s", overlay_attr)
            self.fabric.add_fabric_event("failed", "unable to determine overlay-1 vnid")
            return
       
        # setup slow subscriptions to catch events occurring during build
        self.slow_subscription.subscribe(blocking=False)

        self.fabric.add_fabric_event(init_str, "collecting base managed objects")
        if not self.build_mo():
            self.fabric.add_fabric_event("failed", "failed to collect MOs")
            return

        # build node db and vpc db
        self.fabric.add_fabric_event(init_str, "building node db")
        if not self.build_node_db():
            self.fabric.add_fabric_event("failed", "failed to build node db")
            return
        if not self.build_vpc_db():
            self.fabric.add_fabric_event("failed", "failed to build node pc to vpc db")
            return

        # build tunnel db
        self.fabric.add_fabric_event(init_str, "building tunnel db")
        if not self.build_tunnel_db():
            self.fabric.add_fabric_event("failed", "failed to build tunnel db")
            return

        # build vnid db along with vnsLIfCtxToBD db which relies on vnid db
        self.fabric.add_fabric_event(init_str, "building vnid db")
        if not self.build_vnid_db():
            self.fabric.add_fabric_event("failed", "failed to build vnid db")
            return
        if not self.build_ept_vns_rs_lif_ctx_to_bd_db():
            self.fabric.add_fabric_event("failed", "failed to build vnsLIfCtxToBD db")
            return

        # build epg db
        self.fabric.add_fabric_event(init_str, "building epg db")
        if not self.build_epg_db():
            self.fabric.add_fabric_event("failed", "failed to build epg db")
            return

        # build subnet db
        self.fabric.add_fabric_event(init_str, "building subnet db")
        if not self.build_subnet_db():
            self.fabric.add_fabric_event("failed", "failed to build subnet db")
            return

        # setup epm subscriptions to catch events occurring during epm build
        #   self.epm_subscription.subscribe(blocking=False)
        # TODO - build endpoint database

        # subscriber running
        self.fabric.add_fabric_event("running")
        self.initializing = False

        # ensure that all subscriptions are active
        while True:
            if not self.slow_subscription.is_alive():
                logger.warn("slow subscription no longer alive for %s", self.fabric.fabric)
                self.fabric.add_fabric_event("failed", "subscription no longer alive")
                return
            if False and not self.epm_subscription.is_alive():
                logger.warn("epm subscription no longer alive for %s", self.fabric.fabric)
                self.fabric.add_fabric_event("failed", "subscription no longer alive")
                return
            time.sleep(self.subscription_check_interval)

    def hard_restart(self, reason=""):
        """ send msg to manager for fabric restart """
        logger.warn("restarting fabric monitor '%s': %s", self.fabric.fabric, reason)
        self.fabric.add_fabric_event("restarting", reason)
        # try to kill local subscriptions first
        try:
            self.stopped = True
            reason = "restarting: %s" % reason
            data = {"fabric":self.fabric.fabric, "reason":reason}
            msg = eptMsg(MSG_TYPE.FABRIC_RESTART,data=data)
            with self.manager_ctrl_channel_lock:
                self.redis.publish(MANAGER_CTRL_CHANNEL, msg.jsonify())
        finally:
            self.slow_subscription.unsubscribe()
            self.epm_subscription.unsubscribe()

    def soft_restart(self, ts=None, reason=""):
        """ soft restart sets initializing to True to block new updates along with restarting 
            slow_subscriptions.  A subset of tables are rebuilt which is much faster than a hard
            restart which requires updates to names (epg and vnid db), subnet db, and most 
            importantly endpoint db.
            The following tables are rebuilt in soft restart:
                - eptNode
                - eptTunnel
                - eptVpc
        """
        logger.debug("soft restart requested: %s", reason)
        if ts is not None and self.soft_restart_ts > ts:
            logger.debug("skipping stale soft_restart request (%.3f > %.3f)",self.soft_restart_ts,ts)
            return 

        init_str = "re-initializing"
        self.initializing = True
        self.slow_subscription.restart(blocking=False)

        # build node db and vpc db
        self.fabric.add_fabric_event("soft-reset", reason)
        self.fabric.add_fabric_event(init_str, "building node db")
        if not self.build_node_db():
            self.fabric.add_fabric_event("failed", "failed to build node db")
            return self.hard_restart("failed to build node db")
        if not self.build_vpc_db():
            self.fabric.add_fabric_event("failed", "failed to build node pc to vpc db")
            return self.hard_restart("failed to build node pc to vpc db")

        # build tunnel db
        self.fabric.add_fabric_event(init_str, "building tunnel db")
        if not self.build_tunnel_db():
            self.fabric.add_fabric_event("failed", "failed to build tunnel db")
            return self.hard_restart("failed to build tunnel db")

        # clear appropriate caches
        self.send_flush(eptNode)
        self.send_flush(eptVpc)
        self.send_flush(eptTunnel)

        self.fabric.add_fabric_event("running")
        self.initializing = False

    def send_msg(self, msg):
        """ send eptMsgWork to worker via manager work queue """
        # validate that 'fabric' is ALWAYS set on any work
        msg.fabric = self.fabric.fabric
        with self.manager_work_queue_lock:
            self.redis.rpush(MANAGER_WORK_QUEUE, msg.jsonify())

    def send_flush(self, collection):
        """ send flush message to workers for provided collection """
        logger.info("flush %s", collection._classname)
        # node addr of 0 is broadcast to all nodes of provided role
        msg = eptMsgWork(0, "worker", {"cache": collection._classname}, WORK_TYPE.FLUSH_CACHE)
        msg.qnum = 0    # highest priority queue
        self.send_msg(msg)

    def parse_event(self, event):
        """ return list of (classname, attr) objects from subscription event including _ts attribute
            representing timestamp when event was received
        """
        events = []
        try:
            for e in event["imdata"]:
                classname = e.keys()[0]
                if "attributes" in e[classname]:
                        attr = e[classname]["attributes"]
                        if "_ts" in event: 
                            attr["_ts"] = event["_ts"]
                        else:
                            attr["_ts"] = time.time()
                        events.append((classname, attr))
                else:
                    logger.warn("invalid event: %s", e)
        except Exception as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        return events

    def handle_event(self, event):
        """ generic handler to call appropriate handler based on event classname
            this will also enque events into buffer until intialization has completed
        """
        logger.debug("event: %s", event)
        if self.stopped:
            logger.debug("ignoring event (subscriber stopped and waiting for reset)")
            return
        if self.initializing:
            self.pending_events.append(event)
            return
        try:
            for (classname, attr) in self.parse_events(event):
                if classname not in self.handlers:
                    logger.warn("no event handler defined for classname: %s", classname)
                else:
                    return self.handlers[classname](classname, attr)
        except Exception as e:
            logger.error("Traceback:\n%s", traceback.format_exc())

    def handle_std_mo_event(self, event):
        """ 
        """

    def build_mo(self):
        """ build managed objects for defined classes """
        for mo in self.mo_classes:
            # import the object and add to slow_interest subscription list
            logger.debug("importing: %s", mo)
            mod = import_module(".%s" % mo, "app.models.aci.mo")
            MO = getattr(mod, mo)
            MO.rebuild(self.fabric, session=self.session)
        return True

    def initialize_generic_db_collection(self, restObject, classname, attribute_map, regex_map={}, 
            set_ts=False, flush=False):
        """ most of the initialization is similar steps:
                - delete current objects for restObject
                - perform class query for classname
                - loop through results and add interesting attributes to obj and then perform bulk
                  update into db
            this function assumes all objects have 'fabric' as one of the key attributes

            attribute_map must be a dict in the following format: {
                "db-attribute1-name": "ACI-MO-ATTRIBUTE1"
                "db-attribute2-name": "ACI-MO-ATTRIBUTE2"
                ...
            }
            only the attributes provided in the attribute map will be added to the db object

            regex_map is a dict of db-attribute-name to regex.  If present, then regex is used to 
            validate the attribute (with warning displayed if not captured) along with extracting
            relevant data.  regex must contain a capture group "value" else it is only used for
            validating the attribute.  example {
                "db-attribute1-name": "node-(?P<value>[0-9]+)/"
            }

            set_ts is boolean.  If true then each object will have timestamp set to 'now'

            flush is boolean. Set to true to delete current entries in db before insert

            return bool success
        """
        data = get_class(self.session, classname)
        if data is None:
            logger.warn("failed to get data for classname %s", classname)
            return False

        ts = time.time()
        bulk_objects = []
        for obj in data:
            if type(obj) is dict and len(obj)>0:
                cname = obj.keys()[0]
                if "attributes" in obj[cname]:
                    attr = obj[cname]["attributes"]
                    db_obj = {"fabric": self.fabric.fabric}
                    for db_attr, o_attr in attribute_map.items():
                        if o_attr in attr:
                            # check for regex_map
                            if db_attr in regex_map:
                                r1 = re.search(regex_map[db_attr], attr[o_attr])
                                if r1:
                                    if "value" in r1.groupdict():
                                        db_obj[db_attr] = r1.group("value")
                                    else: 
                                        db_obj[attr] = attr[o_attr]
                                else:
                                    logger.warn("%s value %s does not match regex %s", o_attr,
                                            attr[o_attr], regex_map[db_attr])
                                    db_obj = {}
                                    break
                            else:
                                db_obj[db_attr] = attr[o_attr]
                    if len(db_obj)>1:
                        if set_ts: db_obj["ts"] = ts
                        bulk_objects.append(restObject(**db_obj))
                    else:
                        logger.debug("no interesting attributes found for %s: %s", classname, obj)
                else:
                    logger.warn("invalid %s object: %s (no attributes)", classname, obj)
            else:
                logger.warn("invalid %s object: %s (empty dict)", classname, obj)

        # flush right before insert to minimize time of empty table
        if flush:
            logger.debug("flushing entries in %s for fabric %s",restObject._classname,self.fabric.fabric)
            restObject.delete(_filters={"fabric":self.fabric.fabric})
        if len(bulk_objects)>0:
            restObject.bulk_save(bulk_objects, skip_validation=False)
        else:
            logger.debug("no objects of %s to insert", classname)
        return True
    
    def build_node_db(self):
        """ initialize node collection and vpc nodes. return bool success """
        logger.debug("initializing node db")
        if not self.initialize_generic_db_collection(eptNode, "topSystem", {
                "addr": "address",
                "name": "name",
                "node": "id",
                "oob_addr": "oobMgmtAddr",
                "pod_id": "podId",
                "role": "role",
                "state": "state",
            }, flush=True):
            logger.warn("failed to initialize node db from topSystem")
            return False

        # maintain list of all nodes for id to addr lookup 
        all_nodes = {}
        for n in eptNode.find(fabric=self.fabric.fabric):
            all_nodes[n.node] = n

        # create pseudo node for each vpc group from fabricAutoGEp and fabricExplicitGEp each of 
        # which contains fabricNodePEp
        vpc_type = "fabricExplicitGEp"
        node_ep = "fabricNodePEp"
        data = get_class(self.session, vpc_type, rspSubtree="full", rspSubtreeClass=node_ep)
        if data is None or len(data) == 0:
            logger.debug("no vpcs found for fabricExplicitGEp, checking fabricAutoGEp")
            vpc_type = "fabricAutoGEp"
            data = get_class(self.session, vpc_type, rspSubtree="full", rspSubtreeClass=node_ep)
            if data is None or len(data) == 0:
                logger.debug("no vpc configuration found")
                return True

        # build all known vpc groups
        bulk_objects = []
        for obj in data:
            if vpc_type in obj and "attributes" in obj[vpc_type]:
                attr = obj[vpc_type]["attributes"]
                if "virtualIp" in attr and "name" in attr and "dn" in attr:
                    name = attr["name"]
                    addr = re.sub("/[0-9]+$", "", attr["virtualIp"])
                    # get children node_ep (expect exactly 2)
                    child_nodes = []
                    if "children" in obj[vpc_type]:
                        for cobj in obj[vpc_type]["children"]:
                            if node_ep in cobj and "attributes" in cobj[node_ep]:
                                cattr = cobj[node_ep]["attributes"]
                                if "id" in cattr and "peerIp" in cattr:
                                    peer_ip = re.sub("/[0-9]+$", "", cattr["peerIp"])
                                    node_id = int(cattr["id"])
                                    if node_id in all_nodes:
                                        child_nodes.append({
                                            "local_node": all_nodes[node_id]
                                        })
                                    else:
                                        logger.warn("unknown node id %s", node_id)
                                else:
                                    logger.warn("invalid %s object: %s", node_ep, cobj)
                    if len(child_nodes) == 2:
                        vpc_domain_id = get_vpc_domain_id(
                            child_nodes[0]["local_node"].node,
                            child_nodes[1]["local_node"].node,
                        )
                        bulk_objects.append(eptNode(fabric=self.fabric.fabric,
                            addr=addr,
                            name=name,
                            node=vpc_domain_id,
                            pod_id=child_nodes[0]["local_node"].pod_id,
                            role="vpc",
                            state="in-service",
                            nodes=[
                                {
                                    "node": child_nodes[0]["local_node"].node,
                                    "addr": child_nodes[0]["local_node"].addr,
                                },
                                {
                                    "node": child_nodes[1]["local_node"].node,
                                    "addr": child_nodes[1]["local_node"].addr,
                                },
                            ],
                        ))
                    else:
                        logger.warn("expected 2 %s child objects: %s", node_ep,obj)
                else:
                    logger.warn("invalid %s object: %s", vpc_type, obj)
        
        if len(bulk_objects)>0:
            eptNode.bulk_save(bulk_objects, skip_validation=False)
        return True

    def build_vpc_db(self):
        """ build port-channel to vpc interface mapping. return bool success """
        logger.debug("initializing vpc db")
        if self.initialize_generic_db_collection(eptVpc, "vpcRsVpcConf", {
                "node": "dn",
                "intf": "tSKey",
                "vpc": "parentSKey",
            }, set_ts = True, flush=True, regex_map ={
                "node": "topology/pod-[0-9]+/node-(?P<value>[0-9]+)/",
            }):
            self.vpc_rebuild_ts = time.time()
            return True
        return False

    def build_tunnel_db(self):
        """ initialize tunnel db. return bool success """
        logger.debug("initializing tunnel db")
        return self.initialize_generic_db_collection(eptTunnel, "tunnelIf", {
                "node": "dn",
                "intf": "id",
                "dst": "dest",
                "src": "src",
                "status": "operSt",
                "encap": "tType",
                "flags": "type",
            }, set_ts=True, flush=True, regex_map = {
                "node": "topology/pod-[0-9]+/node-(?P<value>[0-9]+)/",
                "src": "(?P<value>[^/]+)(/[0-9]+)?",
            })

    def build_vnid_db(self):
        """ initialize vnid database. return bool success
            vnid objects include the following:
                fvCtx (vrf)
                fvBD (BD)
                fvSvcBD (copy-service BD)
                l3extExtEncapAllocator (external BD)
        """
        logger.debug("initializing vnid db")
       
        # handle fvCtx
        logger.debug("bulding vnid from fvCtx")
        if not self.initialize_generic_db_collection(eptVnid, "fvCtx", {
                "vnid": "scope",
                "vrf": "scope",
                "pctag": "pcTag",
                "name": "dn",
            }, set_ts=True, flush=True):
            logger.warn("failed to initialize vnid db for fvCtx")
            return False

        # handle fvBD and fvSvcBD
        for classname in ["fvBD", "fvSvcBD"]:
            logger.debug("bulding vnid from %s", classname)
            if not self.initialize_generic_db_collection(eptVnid, classname, {
                    "vnid": "seg",
                    "vrf": "scope",
                    "pctag": "pcTag",
                    "name": "dn",
                }, set_ts=True, flush=False):
                logger.warn("failed to initialize vnid db for %s", classname)
                return False

        # dict of name (vrf/bd) to vnid for quick lookup
        logger.debug("bulding vnid from l3extExtEncapAllocator")
        vnids = {}  
        for v in eptVnid.find(fabric=self.fabric.fabric): 
            vnids[v.name] = v.vnid
        # handle l3extExtEncapAllocator (external BD) which requires second lookup for vrf 
        bulk_objects = []
        data = get_class(self.session, "l3extOut", rspSubtree="full", 
                                    rspSubtreeClass="l3extExtEncapAllocator,l3extRsEctx")
        ts = time.time()
        if data is not None and len(data)>0:
            for obj in data:
                ext_bd = []
                ext_vrf = None
                cname = obj.keys()[0]
                dn = obj[cname]["attributes"]["dn"]
                if "children" in obj[cname] and len(obj[cname]["children"]) > 0:
                    for cobj in obj[cname]["children"]:
                        cname = cobj.keys()[0]
                        attr = cobj[cname]["attributes"]
                        if cname == "l3extRsEctx" and "tDn" in attr:
                            if attr["tDn"] in vnids:
                                ext_vrf = vnids[attr["tDn"]]
                            else:
                                logger.warn("unknown vrf %s in l3extRxEctx: %s", attr["tDn"], attr)
                        if cname == "l3extExtEncapAllocator":
                            ext_bd.append(eptVnid(
                                fabric = self.fabric.fabric,
                                vnid = int(re.sub("vxlan-","", attr["extEncap"])),
                                name = "%s/encap-[%s]" % (dn, attr["encap"]),
                                encap = attr["encap"],
                                ts = ts,
                            ))
                    if ext_vrf is not None:
                        for bd in ext_bd:
                            bd.vrf = ext_vrf
                            bulk_objects.append(bd)
                    else:
                        logger.warn("unable to add (%s) external BDs vnids, vrf not set",len(ext_bd))

        if len(bulk_objects)>0:
            eptVnid.bulk_save(bulk_objects, skip_validation=False)
        return True

    def build_ept_vns_rs_lif_ctx_to_bd_db(self):
        """ initialize eptVnsRsLIfCtxToBD database. return bool success """
        logger.debug("initializing eptVnsRsLIfCtxToBD db")
        if not self.initialize_generic_db_collection(eptVnsRsLIfCtxToBD, "vnsRsLIfCtxToBD", {
                "name": "dn",
                "bd_dn": "tDn",
            }, set_ts=True, flush=True):
            logger.warn("failed to initialize eptVnsRsLIfCtxToBD db")
            return False
        # need to map bd to vnid
        bulk_objects = []
        vnids = {}      # indexed by bd/vrf name (dn), contains only vnid
        for v in eptVnid.find(fabric=self.fabric.fabric): 
            vnids[v.name] = v.vnid
        for vns in eptVnsRsLIfCtxToBD.find(fabric=self.fabric.fabric):
            if vns.bd_dn in vnids:
                vns.bd = vnids[vns.bd_dn]
                bulk_objects.append(vns)
            else:
                logger.warn("failed to map bd for %s: '%s'", vns.name, vns.bd_dn)

        if len(bulk_objects)>0:
            # only adding vnid here which was validated from eptVnid so no validation required
            eptVnsRsLIfCtxToBD.bulk_save(bulk_objects, skip_validation=True)
        return True

    def build_epg_db(self):
        """ initialize epg database. return bool success
            epg objects include the following (all instances of fvEPg)
                fvAEPg      - normal epg            (fvRsBd - map to fvBD)
                mgmtInb     - inband mgmt epg       (mgmtRsMgmtBD - map to fvBD)
                vnsEPpInfo  - epg from l4 graph     (vnsRsEPpInfoToBD - map to fvBD)
                l3extInstP  - external epg          (no BD)
        """
        logger.debug("initializing epg db")
        if not self.initialize_generic_db_collection(eptEpg, "fvEPg", {
                "vrf": "scope",
                "pctag": "pcTag",
                "name": "dn",
                "is_attr_based": "isAttrBasedEPg",
            }, set_ts=True, flush=True):
            logger.warn("failed to initialize epg db from fvEPg")
            return False
      
        logger.debug("mapping epg to bd vnid")
        # need to build mapping of epg to bd. to do so need to get the dn of the BD for each epg
        # and then lookup into vnids table for bd name to get bd vnid to merge into epg table
        bulk_object_keys = {}   # dict to prevent duplicate addition of object to bulk_objects
        bulk_objects = []
        vnids = {}      # indexed by bd/vrf name (dn), contains only vnid
        epgs = {}       # indexed by epg name (dn), contains full object
        for v in eptVnid.find(fabric=self.fabric.fabric): 
            vnids[v.name] = v.vnid
        for e in eptEpg.find(fabric=self.fabric.fabric):
            epgs[e.name] = e
        for classname in ["fvRsBd", "vnsRsEPpInfoToBD", "mgmtRsMgmtBD"]:
            data = get_class(self.session, classname)
            if data is None:
                logger.warn("failed to get data for classname: %s", classname)
                continue
            for obj in data:
                cname = obj.keys()[0]
                attr = obj[cname]["attributes"]
                if "tDn" not in attr or "dn" not in attr:
                    logger.warn("invalid %s object (missing dn/tDn): %s", classname, obj)
                    continue
                epg_name = re.sub("/(rsbd|rsEPpInfoToBD|rsmgmtBD)$", "", attr["dn"])
                bd_name = attr["tDn"]
                if epg_name not in epgs:
                    logger.warn("cannot map bd to unknown epg '%s' from '%s'", epg_name, classname)
                    continue
                if bd_name not in vnids:
                    logger.warn("cannot map epg %s to unknown bd '%s'", epg_name, bd_name)
                    continue
                epgs[epg_name].bd = vnids[bd_name]
                if epg_name not in bulk_object_keys:
                    bulk_object_keys[epg_name] = 1
                    bulk_objects.append(epgs[epg_name])

        if len(bulk_objects)>0:
            # only adding vnid here which was validated from eptVnid so no validation required
            eptEpg.bulk_save(bulk_objects, skip_validation=True)
        return True

    def build_subnet_db(self):
        """ build subnet db 
            Only two objects that we care about but they can come from a few different places:
                - fvSubnet
                    - fvBD, fvAEPg
                      vnsEPpInfo and vnsLIfCtx where the latter requires vnsRsLIfCtxToBD lookup
                - fvIpAttr
                    - fvAEPg
        """
        logger.debug("initializing subnet db")

        # use subnet dn as lookup into vnid and epg table to determine corresponding bd vnid
        # yes, we're doing duplicate db lookup as build_epg_db but db lookup on init is minimum
        # performance hit even with max scale
        vnids = {}
        epgs = {}
        for v in eptVnid.find(fabric=self.fabric.fabric): 
            vnids[v.name] = v.vnid
        for e in eptEpg.find(fabric=self.fabric.fabric):
            # we only care about the bd vnid, only add to epgs list if a non-zero value is present
            if e.bd != 0: epgs[e.name] = e.bd
        # although not technically an epg, eptVnsLIfCtxToBD contains a mapping to bd that we need
        for e in eptVnsRsLIfCtxToBD.find(fabric=self.fabric.fabric):
            if e.bd != 0: epgs[e.parent] = e.bd

        bulk_objects = []
        # should now have all objects that would contain a subnet 
        for classname in ["fvSubnet", "fvIpAttr"]:
            data = get_class(self.session, classname)
            ts = time.time()
            if data is None:
                logger.warn("failed to get data for classname: %s", classname)
                continue
            for obj in data:
                cname = obj.keys()[0]
                attr = obj[cname]["attributes"]
                if "ip" not in attr or "dn" not in attr:
                    logger.warn("invalid %s object (missing dn/ip): %s", classname, obj)
                    continue
                if attr["ip"] == "0.0.0.0" or "usefvSubnet" in attr and attr["usefvSubnet"]=="yes":
                    logger.debug("skipping invalid subnet for %s, %s", attr["ip"], attr["dn"])
                else:
                    dn = re.sub("(/crtrn/ipattr-.+$|/subnet-\[[^]]+\]$)","", attr["dn"])
                    # usually in bd so check vnid first and then epg and then vns
                    bd_vnid = None
                    if dn in vnids:
                        bd_vnid = vnids[dn]
                    elif dn in epgs:
                        bd_vnid = epgs[dn]
                    if bd_vnid is not None:
                        # we support fvSubnet on BD and EPG for shared services so duplicate subnet
                        # can exist. unique index is disabled on eptSubnet to support this... 
                        bulk_objects.append(eptSubnet(
                            fabric = self.fabric.fabric,
                            bd = bd_vnid,
                            name = attr["dn"],
                            subnet = attr["ip"],
                            ts = ts
                        ))
                    else:
                        logger.warn("failed to map subnet '%s' (%s) to a bd", attr["dn"], dn)

        logger.debug("flushing entries in %s for fabric %s",eptSubnet._classname,self.fabric.fabric)
        eptSubnet.delete(_filters={"fabric":self.fabric.fabric})
        if len(bulk_objects)>0:
            eptSubnet.bulk_save(bulk_objects, skip_validation=False)
        return True

    def handle_subnet_event(self, classname, attr):
        """ handle subnet event for fvSubnet and fvIpAttr
                - fvSubnet only expects created or deleted events
                    TODO: decide if we want to handle ctrl:no-default-gateway for fvSubnet
                - fvIpAttr can be created/deleted/modified
                    if modified and usefvSubnet is set to yes then corresponding subnet will be 
                    deleted from eptSubnet db.  This can cause an issue if user is using API and 
                    toggles usefvSubnet (no -> yes -> no).  Here a db entry will not exist but the
                    subnet needs to be added.  An API refresh is required to get the full object

            for create events, use parent dn as lookup into either vnid, epg, or vnsRsLifCtxToBD 
            tables for vnid

            for delete/modify events, use dn as lookup against subnet 'name' to find subnet. Even
            if there are duplicate bd/subnet combindations, the 'name' will be unique.

            for determining which table to perform lookup for fvSubnet (fvIpAttr always epg table)
            fvBD:
                uni/tn-{name}/BD-{name}
                uni/tn-{name}/svcBD-{name}
            fvAEPg:
                uni/tn-{name}/ap-{name}/epg-{name}
            vnsEPpInfo:
                uni/tn-{name}/LDevInst-{[priKey]}-ctx-{ctxName}/G-{graphRn}-N-{nodeRn}-C-{connRn}
                uni/vDev-{[priKey]}-tn-{[tnDn]}-ctx-{ctxName}/rndrInfo/eppContr/G-{graphRn}-N-{nodeRn}-C-{connRn}
            vnsLIfCtx:
                uni/tn-{name}/ldevCtx-c-{ctrctNameOrLbl}-g-{graphNameOrLbl}-n-{nodeNameOrLbl}/lIfCtx-c-{connNameOrLbl}

        """
        logger.debug("handle subnet event: %s", attr["dn"])
        flush = False
        dn = re.sub("(/crtrn/ipattr-.+$|/subnet-\[[^]]+\]$)","", attr["dn"])
        if attr["status"] == "created":
            bd_vnid = 0
            if classname == "fvIpAttr":
                logger.debug("lookup eptEpg for %s", dn)
                obj = eptEpg.find(name=dn)
            elif "/BD-" in dn or "/svcBD-" in dn:
                logger.debug("lookup eptVnid for %s", dn)
                obj = eptVnid.find(name=dn)
            elif "/lIfCtx-" in dn:
                logger.debug("lookup eptVnsRsLIfCtxToBD for %s", dn)
                obj = eptVnsRsLIfCtxToBD.find(parent=dn)
            else:
                logger.debug("(catchall) lookup eptEpg for %s", dn)
                obj = eptEpg.find(name=dn)
            if len(obj)==0:
                logger.warn("unable to determine bd vnid for subnet: %s", attr["dn"])
                return
            # add to db if does not already exists
            obj = obj[0]
            if isinstance(obj, eptVnid): bd = obj.vnid
            else: bd = obj.bd
            subnet=eptSubnet.load(fabric=self.fabric.fabric,bd=bd,subnet=attr["ip"],name=attr["dn"])
            if subnet.exists():
                logger.debug("ignoring create for existing subnet: %s", dn)
                # update timestamp if more recent then db entry
                if subnet.ts < attr["_ts"]:
                    subnet.ts = attr["_ts"]
                    subnet.save()
                return
            else:
                subnet.ts = attr["_ts"]
                subnet.save()
                flush = True
        elif attr["status"] == "deleted":
            subnet = eptSubnet.load(fabric=self.fabric.fabric, name=attr["dn"])
            if not subnet.exists() or subnet.ts > attr["_ts"]:
                logger.debug("ignorning delete for subnet that does not exist: %s", attr["dn"])
            elif subnet.ts > attr["_ts"]:
                logger.debug("ignorning old delete event for subnet %s (%s < %s)",
                        attr["dn"], attr["_ts"],subnet.ts)
            else:
                subnet.remove()
                flush = True
        elif attr["status"] == "modified":
            subnet = eptSubnet.load(fabric=self.fabric.fabric, name=attr["dn"])
            if classname == "fvSubnet":
                logger.debug("ignoring modify events for fvSubnet")
            elif subnet.exists() and subnet.ts > attr["_ts"]:
                logger.debug("ignorning old modify event for subnet %s (%s < %s)",
                        attr["dn"], attr["_ts"], subnet.ts)
            else:
                # need to do refresh on object - easier than tracking state
                fvIp = get_attributes(session=self.session, dn=attr["dn"])
                ts = time.time()
                if fvIp is None: 
                    logger.debug("failed to refresh state for '%s' (deleted?)", attr["dn"])
                    if subnet.exists():
                        subnet.remove()
                        flush = True
                elif fvIp["ip"] == "0.0.0.0" or fvIp["usefvSubnet"] == "yes":
                    if subnet.exists():
                        subnet.remove()
                        flush = True
                else:
                    # need to determine bd, lookup will be against eptEpg table
                    subnet.subnet = fvIp["ip"]
                    obj = eptEpg.find(name=dn)
                    if len(obj) == 0:
                        logger.warn("unable to determine bd vnid for subnet: %s", attr["dn"])
                        return
                    subnet.bd = obj[0].bd
                    subnet.ts = ts
                    subnet.save()
                    flush = True

        if flush:
            logger.debug("subnet change requiring flush detected for %s", self.fabric.fabric)
            self.send_flush(eptSubnet)

    def handle_fabric_prot_pol(self, classname, attr):
        """ if pairT changes in fabricProtPol then trigger hard restart """
        logger.debug("handle fabricProtPol event: %s", attr["pairT"])
        if "pairT" in attr and attr["pairT"] != self.settings.vpc_pair_type:
            msg="fabricProtPol changed from %s to %s" % (self.settings.vpc_pair_type,attr["pairT"])
            logger.warn(msg)
            self.hard_restart(msg)
        else:
            logger.debug("no change in fabricProtPol")

    def handle_fabric_group_ep(self, classname, attr):
        """ fabricExplicitGEp or fabricAutoGEp update requires unconditional soft restart """
        logger.debug("handle %s event", classname)
        self.soft_restart(ts=attr["_ts"], reason="(%s) vpc domain update" % classname)

    def handle_fabric_node(self, classname, attr):
        """ handle events for fabricNode
            If a new leaf becomes active then trigger a hard restart to rebuild endpoint database
            as there's no way of knowing when endpoint events were missed on the new node (also,
            we need to restart both slow and epm subscriptions to get events from the new node).
            If an existing leaf becomes inactive, then create delete jobs for all endpoint learns 
            for this leaf
        """
        logger.debug("handle fabricNode event: %s", attr["dn"])
        if "dn" in attr and "fabricSt" in attr:
            r1 = re.search("topology/pod-(?P<pod>[0-9]+)/node-(?P<node>[0-9]+)", attr["dn"])
            status = attr["fabricSt"]
            if r1 is None:
                logger.warn("failed to extract node id from fabricNode dn: %s", attr["dn"])
                return
            # get db entry for this node
            node = eptNode.load(fabric=self.fabric.fabric, node=int(r1.group("node")))
            if node.exists():
                if node.role != "leaf":
                    logger.debug("ignoring fabricNode event for '%s'", node.role)
                else:
                    # if this is an active event, then trigger a hard restart else trigger pseudo
                    # delete jobs for all previous entries on node.  This includes XRs to account
                    # for bounce along with generally cleanup of node state.
                    if status == "active":
                        self.hard_restart(reason="leaf '%s' became active" % node.node)
                    else:
                        logger.debug("node %s '%s', sending watch_node event", node.node, status)
                        data = {"pod": node.pod_id, "node": node.node}
                        msg = eptMsgWork("node-%s" % node.node, "watcher",data,WORK_TYPE.WATCH_NODE)
                        self.send_msg(msg)
            else:
                if status != "active":
                    logger.debug("ignorning '%s' event for unknown node: %s",status,r1.group("node"))
                else:
                    # a new node became active, double check that is a leaf and if so trigger a 
                    # hard restart
                    new_node_dn = "topology/pod-%s/node-%s" % (r1.group("pod"), r1.group("node"))
                    new_attr = get_attributes(session=self.session, dn=new_node_dn)
                    if new_attr is not None and "role" in new_attr and new_attr["role"] == "leaf":
                        self.hard_restart(reason="new leaf '%s' became active" % r1.group("node"))
                    else:
                        logger.debug("ignorning active event for non-leaf")
        else:
            logger.debug("ignoring fabricNode event (fabricSt or dn not present in attributes)")

    def handle_rs_vpc_conf_event(self, classname, attr):
        """ handle updates to vpcRsVpcConf which provide mapping of pc to vpc
            unfortunately this subscription is unreliable (i.e., delete + create only returns a
            delete event), therefore we will use full eptVpc rebuild on any event.  This is 
            inefficient but only occurs on user config event so relatively rare...
        """
        logger.debug("handle %s event", classname)
        if attr["_ts"] > self.vpc_rebuild_ts:
            self.build_vpc_db()
            self.send_flush(eptVpc)
        else:
            logger.debug("ignorning vpc rebuild as %0.3f > %0.3f", self.vpc_rebuild_ts, attr["_ts"])

    def handle_vnid_event(self, classname, attr):
        """ handle vnid updates for fvCtx, fvBD, and fvSvcBD. Refresh required on modified events
            for unknown objects
        """
        logger.debug("handle vnid event for %s", classname)
        orig_vnid = None
        obj = eptVnid.find(fabric=self.fabric.fabric, name=attr["dn"])
        if len(obj) > 0: 
            obj = obj[0]
            logger.debug("existing eptVnid object: %s", obj)
            if classname != "fvCtx": orig_vnid = obj.vnid
        else:  
            obj = eptVnid(fabric=self.fabric.fabric, name=attr["dn"])
            logger.debug("creating new eptVnid: %s", attr["dn"])
        if obj.exists() and obj.ts > attr["_ts"]:
            logger.debug("ignoring old event (%0.3f > %0.3f)", obj.ts, attr["_ts"])
            return

        vrf = attr.get("scope", None)
        pctag = attr.get("pcTag", None)
        if classname == "fvCtx":  vnid = attr.get("scope", None)
        else: vnid = attr.get("seg", None)
        obj.ts = attr["_ts"]

        if attr["status"] == "created" or attr["status"] == "modified":
            # don't necessarily have everything we need on create but will always have vnid
            # if we don't have vnid and object does not exist, then need to do a refresh
            if vnid is None and not obj.exists():
                logger.debug("refreshing %s", attr["dn"])
                refresh = get_attributes(session=self.session, dn=attr["dn"])
                obj.vrf = refresh["scope"]
                obj.pctag = refresh["pcTag"]
                if classname == "fvCtx": obj.vnid = refresh["scope"]
                else: obj.vnid = refresh["seg"]
                obj.save()
                obj.reload()  # ensures that attributes points to post-validator values
            else:
                if vnid is not None: obj.vnid = vnid
                if vrf is not None: obj.vrf = vrf
                if pctag is not None: obj.pctag = pctag
                obj.save()
                obj.reload()  # ensures that attributes points to post-validator values
            # if the vnid is changed, then need to refresh eptSubnet and eptEpg that have old vnid
            # note, this works as bd vnid is globally unique
            if orig_vnid is not None and obj.vnid != orig_vnid:
                logger.debug("vnid for %s changed from %s to %s", obj.name, orig_vnid, obj.vnid)
                bulk_epg = []
                bulk_subnet = []
                for epg in eptEpg.find(fabric=self.fabric.fabric, bd=orig_vnid):
                    epg.bd = obj.vnid
                    bulk_epg.append(epg)
                if len(bulk_epg) > 0:
                    logger.debug("updating %s eptEpg vnids to %s", len(bulk_epg), obj.vnid)
                    eptEpg.bulk_save(bulk_epg)
                for subnet in eptSubnet.find(fabric=self.fabric.fabric, bd=orig_vnid):
                    subnet.bd = obj.vnid
                    bulk_subnet.append(subnet)
                if len(bulk_subnet) > 0:
                    logger.debug("updating %s eptSubnet vnids to %s", len(bulk_subnet), obj.vnid)
                    eptSubnet.bulk_save(bulk_subnet)

        elif attr["status"] == "deleted":
            if obj.exists():
                logger.debug("deleting existing entry: %s", attr["dn"])
                obj.remove()
            else:
                logger.debug("ignoring delete event for non-existing vnid: %s", attr["dn"])
                return

        # send flush for eptVnid cache on workers
        self.send_flush(eptVnid)
  
