
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
from . ept_epg import eptEpg
from . ept_node import eptNode
from . ept_tunnel import eptTunnel
from . ept_settings import eptSettings
from . ept_subnet import eptSubnet
from . ept_vnid import eptVnid
from . ept_vpc import eptVpc

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
            "fvEPg",        # this includes fvAEPg, l3extInstP, vnsEPpInfo
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

        # get overlay vnid
        overlay_attr = get_attributes(session=self.session, dn="uni/tn-infra/ctx-overlay-1")
        if overlay_attr and "scope" in overlay_attr:
            self.settings.overlay_vnid = int(overlay_attr["scope"])
            self.settings.save()
        else:
            logger.warn("failed to determine overlay vnid: %s", overlay_attr)
            self.fabric.add_fabric_event("failed", "unable to determine overlay-1 vnid")
            return
       
        # setup slow subscriptions to catch events occurring during build
        self.slow_subscription.subscribe(blocking=False)

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

        # build vnid db
        self.fabric.add_fabric_event(init_str, "building vnid db")
        if not self.build_vnid_db():
            self.fabric.add_fabric_event("failed", "failed to build vnid db")
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
        logger.debug("event: %s", event)
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
        return self.initialize_generic_db_collection(eptVpc, "vpcRsVpcConf", {
                "node": "dn",
                "intf": "tSKey",
                "vpc": "parentSKey",
            }, set_ts = True, flush=True, regex_map ={
                "node": "topology/pod-[0-9]+/node-(?P<value>[0-9]+)/",
            })

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

        # build bd mapping for vnsLIfCtx to support service graph subnets
        vns_epg = {}    # indexed by vnsLIfCtx dn with mapping to bd vnid
        data = get_class(self.session, "vnsRsLIfCtxToBD")
        if data is not None and len(data)>0:
            for obj in data:
                cname = obj.keys()[0]
                if "tDn" in obj[cname]["attributes"] and "dn" in obj[cname]["attributes"]:
                    vns_dn = re.sub("/rsLIfCtxToBD$", "", obj[cname]["attributes"]["dn"])
                    bd_dn = obj[cname]["attributes"]["tDn"]
                    if bd_dn in vnids:
                        vns_epg[vns_dn] = vnids[bd_dn]
                    else:
                        logger.warn("unable to map vnsLIfCtx '%s' to unknown bd '%s'",vns_dn,bd_dn)

        dup_check = {}
        dup_count = 0
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
                    elif dn in vns_epg:
                        bd_vnid = vns_epg[dn]
                    if bd_vnid is not None:
                        # we support fvSubnet on BD and EPG for shared services so duplicate subnet
                        # can exist so prevent dup added here which causes db error
                        if bd_vnid not in dup_check: dup_check[bd_vnid] = {}
                        if attr["ip"] not in dup_check[bd_vnid]:
                            dup_check[bd_vnid][attr["ip"]] = 1
                            bulk_objects.append(eptSubnet(
                                fabric = self.fabric.fabric,
                                bd = bd_vnid,
                                subnet = attr["ip"],
                                ts = ts
                            ))
                        else: dup_count+=1
                    else:
                        logger.warn("failed to map subnet '%s' (%s) to a bd", attr["dn"], dn)

        logger.debug("duplicate subnet count: %s", dup_count)
        logger.debug("flushing entries in %s for fabric %s",eptSubnet._classname,self.fabric.fabric)
        eptSubnet.delete(_filters={"fabric":self.fabric.fabric})
        if len(bulk_objects)>0:
            eptSubnet.bulk_save(bulk_objects, skip_validation=False)
        return True


    

