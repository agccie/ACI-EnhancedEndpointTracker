
from ... utils import get_db

from .. utils import get_apic_session
from .. utils import get_attributes
from .. utils import get_class
from .. utils import get_controller_version
from .. utils import parse_apic_version
from .. utils import pretty_print
from .. subscription_ctrl import SubscriptionCtrl

from . common import MINIMUM_SUPPORTED_VERSION
from . common import get_vpc_domain_id
from . ept_node import eptNode
from . ept_tunnel import eptTunnel
from . ept_settings import eptSettings

import logging
import re
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class eptSubscriber(object):
    def __init__(self, fabric):
        # receive instance of Fabric rest object
        self.fabric = fabric
        self.settings = eptSettings.load(fabric=self.fabric.fabric)
        self.initializing = True
        self.db = None
        self.session = None
        self.subscription_check_interval = 5.0   # interval to check subscription health

        # list of pending events received on subscription while in init state
        self.pending_events = []        
        # statically defined classnames in which to subscribe
        # slow subscriptions are classes which we expect a low number of events
        subscription_classes = [
            "fabricProtPol",
            "fabricExplicitGEp",
            "vpcRsVpcConf",
            "fabricNode",
            "fvCtx",
            "fvBD",
            "fvSvcBD",
            "fvEPg",
            "fvRsBd",
            "vnsRsEPpInfoToBD",
            "l3extExtEncapAllocator",
            "fvSubnet",
            "fvIpAttr",
        ]
        # epm subscriptions expect a high volume of events
        epm_subscription_classes = [
            "epmMacEp",
            "epmIpEp",
            "epmRsMacEpToIpEpAtt",
        ]
        # classname to function handler for subscription events
        self.handles = {                
            
        }

        # create subscription object for slow and fast subscriptions
        slow_interest = {}
        epm_interest = {}
        for s in subscription_classes:
            slow_interest[s] = {"handler": self.handle_event}
        for s in epm_subscription_classes:
            epm_interest[s] = {"handler": self.handle_event}

        self.slow_subscription = SubscriptionCtrl(self.fabric, slow_interest, inactive_interval=1)
        self.epm_subscription = SubscriptionCtrl(self.fabric, epm_interest, inactive_interval=0.01)

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        logger.info("starting eptSubscriber for fabric '%s'", self.fabric.fabric)
        try:
            # allocate a unique db connection as this is running in a new process
            self.db = get_db(uniq=True, overwrite_global=True)
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
            self.fabric.add_fabric_event("failed","unknown or unsupported apic version: %s"%version)
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
            self.fabric.add_fabric_event("failed", "unsupported apic version: %s" % version)
            return

        # get overlay vnid
        overlay_attr = get_attributes(session=self.session, dn="uni/tn-infra/ctx-overlay-1")
        if overlay_attr and "scope" in overlay_attr:
            self.settings.overlay_vnid = int(overlay_attr["scope"])
            self.settings.save()
        else:
            logger.warn("failed to determine overlay vnid: %s", overlay_attr)
            self.fabric.add_fabric_event("failed", "unable to determine overlay-1 vnid")
        self.fabric.add_fabric_event(init_str, "overlay vnid 0x%x" % self.settings.overlay_vnid)
       
        # setup slow subscriptions to catch events occurring during build
        self.slow_subscription.subscribe(blocking=False)

        # build node db
        self.fabric.add_fabric_event(init_str, "building node db")
        if not self.build_node_db():
            self.fabric.add_fabric_event("failed", "failed to build node db")
            return

        # build tunnel db
        self.fabric.add_fabric_event(init_str, "building tunnel db")
        if not self.build_tunnel_db():
            self.fabric.add_fabric_event("failed", "failed to build tunnel db")
            return


        # setup epm subscriptions to catch events occurring during epm build
        self.epm_subscription.subscribe(blocking=False)


        # ensure that all subscriptions are active
        while True:
            if not self.slow_subscription.is_alive():
                logger.warn("slow subscription no longer alive for %s", self.fabric.fabric)
                self.fabric.add_fabric_event("failed", "subscription no longer alive")
                return
            if not self.epm_subscription.is_alive():
                logger.warn("epm subscription no longer alive for %s", self.fabric.fabric)
                self.fabric.add_fabric_event("failed", "subscription no longer alive")
                return
            time.sleep(self.subscription_check_interval)

    def handle_event(self, event):
        """ generic handler to call appropriate handler based on event classname
            this will also enque events into buffer until intialization has completed
        """
        if self.initializing:
            self.pending_events.append(event)
            return
        for e in event["imdata"]:
            classname = e.keys()[0]
            if "attributes" in e[classname]:
                if classname not in self.handlers:
                    logger.warn("unexpected classname event received: %s, %s", classname, e)
                else:
                    attr = e[classname]["attributes"]
                    if "_ts" in event: 
                        attr["_ts"] = event["_ts"]
                    else:
                        attr["_ts"] = time.time()
                    return self.handlers[classname](attr)
            else:
                logger.warn("invalid event: %s", e)

    def initialize_generic_db_collection(self, restObject, classname, attribute_map, regex_map={}, 
            set_ts=False):
        """ most of the initialization is similar steps:
                - delete current objects for restObject
                - perform class query for classname
                - loop through results and add interesting attributes to obj and then perform bulk
                  update into db
            this function assumes all objects have 'fabric' as one of the key attributes

            attribute_map must be a dict in the following format: {
                "ACI-MO-ATTRIBUTE1": "db-attribute1-name",
                "ACI-MO-ATTRIBUTE2": "db-attribute2-name",
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

            return bool success
        """
        logger.debug("init collection %s for fabric %s", restObject._classname, self.fabric.fabric)
        restObject.delete(_filters={"fabric":self.fabric.fabric})

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
                    for o_attr, db_attr in attribute_map.items():
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

        if len(bulk_objects)>0:
            restObject.bulk_save(bulk_objects, skip_validation=False)
        else:
            logger.debug("no objects of %s found", classname)
        return True
    
    def build_node_db(self):
        """ initialize node collection and vpc nodes. return bool success """
        logger.debug("initializing node db")
        if not self.initialize_generic_db_collection(eptNode, "topSystem", {
                "address": "addr",
                "name": "name",
                "id": "node",
                "oobMgmtAddr": "oob_addr",
                "podId": "pod_id",
                "role": "role",
                "state": "state",
            }):
            logger.warn("failed to initialize node db from topSystem")
            return False

        # maintain list of all nodes for id to addr lookup 
        all_nodes = {}
        for n in eptNode.load(fabric=self.fabric.fabric, _bulk=True):
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


    def build_tunnel_db(self):
        """ initialize tunnel db
            return bool success
        """
        logger.debug("initializing tunnel db")
        return self.initialize_generic_db_collection(eptTunnel, "tunnelIf", {
                "dn": "node",
                "id": "intf",
                "dest": "dst",
                "src": "src", 
                "operSt": "status",
                "tType": "encap",
                "type": "flags",
            }, set_ts=True, regex_map = {
                "node": "topology/pod-[0-9]+/node-(?P<value>[0-9]+)/",
                "src": "(?P<value>[^/]+)(/[0-9]+)?",
            })

    

