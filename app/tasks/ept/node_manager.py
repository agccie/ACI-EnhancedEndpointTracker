"""
    Node Manager
    @author agossett@cisco.com
"""
from . import utils as ept_utils
import re, time
from pymongo import InsertOne, UpdateOne
from pymongo.errors import BulkWriteError

# setup logger for this package
import logging
logger = logging.getLogger(__name__)
ept_utils.setup_logger(logger)

class Node_Monitor(object):
    """ responsible for monitoring various node aspects with capabilities
        of restarting application if needed or sending message to all workers
        to flush state after database update
        monitors
            vpcRsVpcConf
            fabricProtPol
            tunnelIf
            (need to figure out appropriate topSystem objects...)    
    """
    def __init__(self, fabric, parent, loggeroverride=None):
        global logger
        if loggeroverride is not None: logger = loggeroverride
        self.fabric = fabric
        self.app = ept_utils.get_app()
        self.parent = parent
        self.session = None
        self.initialized = False
        self.vpc_pairT = None
        self.last_session_refresh = 0
        self.session_refresh_time = 60
        if not self.build_initial_state():
            raise Exception("failed to initialize node monitor")
        self.last_restart = time.time()
        self.last_vpc_rebuild = time.time()
        self.initialized = True

    def build_initial_state(self):
        """ build subset of initial fabric state
            returns success boolean
        """
        self.refresh_session()

        # get fabricProtPol to understand vpc changes
        classname = "fabricProtPol"
        js = ept_utils.get_class(self.session, classname)
        if js is None:
            logger.warn("failed to get %s" % classname)
            return False 
        if len(js)!=1 or classname not in js[0] or \
            "attributes" not in js[0][classname] or \
            "pairT" not in js[0][classname]["attributes"]:
            logger.warn("invalid js returned for %s: %s" % (classname,js))
            return False
        self.vpc_pairT = js[0][classname]["attributes"]["pairT"]
        logger.debug("vpc pairing policy: %s" % self.vpc_pairT)

        # no errors encounted
        return True

    def soft_restart(self, event_time, reason=None):
        """ perform a 'soft' restart by rebuilding critical tables and 
            sending a message to clear state on other worker threads.
            this is faster than a full restart as it doesn't involve:
                - name rebuild (ep_vnids, ep_epgs)
                - subnet rebuild
                - endpoint db rebuild
        """ 
        logger.debug("soft restart requested: %s" % reason)
        if event_time is not None and self.last_restart > event_time:
            logger.debug("skipping restart as last restart(%f) > event(%f)",
                self.last_restart, event_time)
            return

        # rebuild required databases
        ept_utils.add_fabric_event(self.fabric, "Soft-reset", reason)
        if not self.build_initial_state():
            self.hard_restart("failed to initialize node monitor")

        ept_utils.add_fabric_event(self.fabric, "Re-initializing", 
            "Re-building node database")
        if not build_initial_node_db(self.fabric, self.session, self.app):
            self.hard_restart("failed to initialize node database")

        ept_utils.add_fabric_event(self.fabric, "Re-initializing", 
            "Re-building tunnel database")
        if not build_initial_tunnel_db(self.fabric, self.session, self.app):
            self.hard_restart("failed to initialize tunnel database")
        
        ept_utils.add_fabric_event(self.fabric, "Re-initializing", 
            "Re-building vpc mapping database")
        if not build_vpc_node_db(self.fabric, self.session, self.app):
            self.hard_restart("failed to initialize vpc database")
        if not build_vpc_config_db(self.fabric, self.session, self.app):
            self.hard_restart("failed to initialize vpc database")

        # clear all caches
        self.parent.clear_worker_cache("node_cache")
        self.parent.clear_worker_cache("tunnel_cache")
        self.parent.clear_worker_cache("pc_cache")
        # force a subscription close event so we can ensure subscription
        # is correctly setup to new node(s) due to proxied nginx issue...
        ept_utils.add_fabric_event(self.fabric, "Running", "")
        self.parent.restart_subscription(reason)

    def hard_restart(self, reason):
        """ force hard restart of application """
        if not self.initialized:
            raise Exception("hard reset during initialization: %s" % reason)
        ept_utils.restart_fabric(self.fabric, reason=reason)

    def handle_fabricProtPol(self, e):
        """ check if fabricProtPol has changed, if so restart application
        """
        classname = "fabricProtPol"
        logger.debug("%s event: %s" % (classname, ept_utils.pretty_print(e)))
        if "imdata" not in e or len(e["imdata"])==0: 
            logger.debug("invalid reply or empty data")
            return
        for event in e["imdata"]:
            if classname in event and "attributes" in event[classname]:
                attr = event[classname]["attributes"]
                if "pairT" in attr and attr["pairT"]!=self.vpc_pairT:
                    logger.error("pairT changed from %s to %s" % (
                        self.vpc_pairT, attr["pairT"])) 
                    self.hard_restart("fabricProtPol update")

    def handle_fabricExplicitGEp(self, e):
        """ delete or create a new vpc domain, triggers a soft restart
        """
        classname = "fabricExplicitGEp"
        logger.debug("%s event: %s" % (classname, ept_utils.pretty_print(e)))
        if "imdata" not in e or len(e["imdata"])==0: 
            logger.debug("invalid reply or empty data")
            return
        for event in e["imdata"]:
            if classname in event and "attributes" in event[classname]:
                # some deleted or created vpc domain
                ts = e["_ts"] if "_ts" in e else time.time()
                self.soft_restart(ts, "(fabricExplicitGEp) vpc domain update")

    def handle_vpcRsVpcConf(self, e):
        """ update ep_vpcs database based on received event """

        # object returns unreliable data (delete + recreate only returns delete)
        # easiest (inefficient) way is to manually re-build on any update that
        # happened after last rebuild completed
        classname = "vpcRsVpcConf"
        logger.debug("%s event: %s" % (classname, ept_utils.pretty_print(e)))
        if "_ts" in e and e["_ts"]<self.last_vpc_rebuild:
            logger.debug("ignoring old event last_vpc_rebuild: %f > %f"%(
                self.last_vpc_rebuild, e["_ts"]))
            return
        logger.debug("rebuild vpc config")
        self.refresh_session()
        build_vpc_config_db(self.fabric, self.session, self.app)
        self.last_vpc_rebuild = time.time()
        self.parent.clear_worker_cache("pc_cache")

    def handle_fabricNode(self, e):
        """ receive fabricNode events - if a new node becomes active then 
            need to rebuild full node state and restart subscription
            returns 
                {"node": "node-id", "status": "active|inactive"}
                None on error
        """
        classname = "fabricNode"
        logger.debug("%s event: %s" % (classname, ept_utils.pretty_print(e)))
        if "imdata" not in e or len(e["imdata"])==0: 
            logger.debug("invalid reply or empty data")
            return
        ret = {"pod":None, "node":None, "status":None}
        node_reg = "topology/pod-(?P<pod>[0-9]+)/node-(?P<node>[0-9]+)"
        rebuild_required = False
        for event in e["imdata"]:
            if classname in event and "attributes" in event[classname]:
                attr = event[classname]["attributes"]
                if "dn" not in attr or "fabricSt" not in attr:
                    logger.debug("skipping event dn/fabricSt missing")
                    continue
                r1 = re.search(node_reg, attr["dn"])
                if r1 is None:
                    logger.warn("failed to parse dn: %s" % attr["dn"])
                    continue
                ret["pod"] = r1.group("pod")
                ret["node"] = r1.group("node")
                ret["status"] = attr["fabricSt"]
                # a new node comes online with 'active' status
                if attr["fabricSt"] == "active":
                    rebuild_required = True
                break

        # unable to parse event or some other error 
        if ret["node"] is None: 
            logger.debug("no valid fabricNode event found")
            return ret

        # database lookup for node to ensure it's a leaf since we
        # aren't monitoring for controller/spine reloads
        key = {"fabric": self.fabric, "id":ret["node"]}
        with self.app.app_context():
            db = self.app.mongo.db
            h = db.ep_nodes.find_one(key)
            if h is not None:
                logger.debug("fabricNode event for node-%s: role:%s" % (
                        ret["node"], h["role"]))
                if h["role"]!="leaf":
                    logger.debug("skipping event for non-leaf role")
                    return None
            else:
                logger.debug("fabricNode event for unknown node")

        if not rebuild_required:
            logger.debug("no node rebuild required")
            return ret
        ts = e["_ts"] if "_ts" in e else time.time()
        self.soft_restart(ts, "(fabricNode) node-%s became active" % (
            ret["node"]))
        return ret

    def handle_name_event(self, e):
        """ receive event for various classes and check if entry exists in 
            database. If ts in database is more recent than event then no 
            action occurs. Else, query the APIC for the full state of the 
            object and update database with new entry
            classes:
                l3extExtEncapAllocator, l3extInstP, fvAEPg, fvBD, fvCtx
                fvRsBd, 
                fvSvcBD, vnsRsEPpInfoToBD, vnsEPpInfo
        """
        logger.debug("named_event: %s" % (ept_utils.pretty_print(e)))
        if "imdata" not in e or len(e["imdata"])==0: 
            logger.debug("invalid reply or empty data")
            return

        # parse the classname and dn
        c = None
        dn = None
        for event in e["imdata"]:
            c = event.keys()[0]
            if "attributes" in event[c]:
                attr = event[c]["attributes"]
                if "dn" not in attr: 
                    logger.warn("dn not present in attributes: %s" % attr)
                    return
                dn = attr["dn"]
                break
        if c is None or dn is None:
            logger.warn("unable to determine class or dn: %s" % e)
            return

        # get the last database entry for this event
        if c == "fvCtx" or c =="fvBD" or c == "fvSvcBD" or \
            c =="l3extExtEncapAllocator":
            table = "ep_vnids"
        elif c == "l3extInstP" or c == "fvAEPg" or c == "vnsEPpInfo":
            table = "ep_epgs"
        elif c == "fvRsBd":
            # update c to normal epg as that is the object we need to now check
            c = "fvAEPg"
            dn = re.sub("/rsbd$", "", dn)
            table = "ep_epgs"
        elif c == "vnsRsEPpInfoToBD":
            # update c to normal epg as that is the object we need to now check
            c = "vnsEPpInfo"
            dn = re.sub("/rsEPpInfoToBD$", "", dn)
            table = "ep_epgs"
        else:
            logger.debug("unexpected class %s" % c)
            return        

        key = {"fabric": self.fabric, "name": dn}
        with self.app.app_context():
            db = self.app.mongo.db
            h = db[table].find_one(key)
            # perform refresh for new entries or if event is more recent than
            # db event
            if h is not None and \
                ("ts" in h and "_ts" in e and e["_ts"]<h["ts"]):
                logger.debug("skipping %s, refresh not required (%s<%s)" % (
                    c, e["_ts"], h["ts"]))
                return
            self.refresh_session()
            js = ept_utils.get_dn(self.session, dn) 
            if js is None: 
                logger.warn("failed to get dn(%s)" % dn)
                return
            logger.debug("refreshed(%s): %s"%(dn,js))
            if c in js and "attributes" in js[c]:
                attr = js[c]["attributes"]
                p = process_name_object(self.fabric, c, attr)
                update = p["key"]

                # merge subset of attributes if present in h but no in update
                merge_attr = ["bd_vnid", "isAttrBasedEPg"]
                if h is not None:
                    for m in merge_attr: 
                        if m in h and len(h[m])>0 and (m not in update or \
                            len(update[m])==0):
                            update[m] = h[m]

                if "_ts" in e: update["ts"] = e["_ts"]
                else: update["ts"] = time.time()
                check = ["name", "vnid", "pcTag"]
                if table == "ep_vnids": check+=["encap", "vrf"]
                # check that refresh state is different than history state
                update_required = False
                if h is not None:
                    for cattr in check:
                        if cattr not in h or h[cattr]!=update[cattr]:
                            logger.debug("update to %s, %s!=%s" % (cattr, 
                                h[cattr],update[cattr]))
                            update_required = True
                            break
                else: update_required = True

                # if class is fvAEPg or vnsEPpInfo, always refresh bd_vnid
                nbv = None
                new_dn = None
                if c == "fvAEPg": new_dn = "%s/rsbd" % dn
                elif c == "vnsEPpInfo": new_dn = "%s/rsEPpInfoToBD" % dn
                if new_dn is not None:
                    nbv=self.refresh_epg_bd_vnid(new_dn,update["bd_vnid"])
                    if nbv is not None: 
                        update_required = True
                        update["bd_vnid"] = nbv
                        # perform any dependent bd update operations
                        self.handle_epg_rsbd_update(dn, nbv)

                if not update_required:
                    logger.debug("no update to %s required" % table)
                    return
                logger.debug("update/insert %s: %s" % (table, update))
                update = {"$set": update}
                r = db[table].update_one(key, update, upsert = True)
            else:
                # dn does not exists so this is delete operation
                if h is None: 
                    logger.debug("ignoring delete, %s not in %s" % (dn,table))
                    return 
                logger.debug("deleting %s from %s" % (dn, table))
                db[table].delete_one(key)

            # assume successful db update, force clear cache
            if table == "ep_epgs":
                self.parent.clear_worker_cache("epgs_cache")
            elif table == "ep_vnids": 
                self.parent.clear_worker_cache("vnids_cache")

    def handle_epg_rsbd_update(self, epg_dn, bd_vnid):
        """ since fvSubnet and fvIpAttr dn's contain epg_dn, easiest way to
            perform update is to do regex based query to get current subnets
            and if corresponding bd_vnid is not the epg's new bd_vnid, remove
            and add to correct bd_vnid
        """ 
        logger.debug("handle epg rsbd update to %s for %s" % (bd_vnid, epg_dn))

        move_count = 0
        bulk_updates = {"ep_subnets":[]}
        reg = "%s\/(crtrn|subnet)" % re.escape(epg_dn)
        key={"fabric":self.fabric,"subnets.dn":{"$regex":reg}}
        with self.app.app_context():
            db = self.app.mongo.db
            for bd_subnet in db.ep_subnets.find(key):
                if bd_subnet["vnid"] == bd_vnid:
                    # vnid is same as current bd_vnid, no move required
                    logger.debug("ignorning new bd_vnid subnets: %s"%bd_vnid)
                    continue 
                for subnet in bd_subnet["subnets"]:
                    if re.search(reg, subnet["dn"]) is None:
                        logger.debug("ignoring bd_vnid(%s) subnet(%s)"%(
                            bd_subnet["vnid"], subnet["dn"]))
                        continue
                    logger.debug("moving subnet(%s) from bd(%s) to bd(%s)"%(
                            subnet["dn"], bd_subnet["vnid"], bd_vnid))
                    bulk_updates["ep_subnets"].append(UpdateOne(
                        {"fabric":self.fabric, "subnets.dn":subnet["dn"]},
                        {"$pull":{"subnets":{"dn":subnet["dn"]}}}))
                    bulk_updates["ep_subnets"].append(UpdateOne(
                        {"fabric": self.fabric, "vnid": bd_vnid},
                        {"$push":{"subnets":{"$each":[subnet]}}}, upsert=True))
                    move_count+= 1
   
        if move_count > 0: 
            r = ept_utils.bulk_update("ep_subnets", bulk_updates, app=self.app)
            logger.debug("moved %s subnets (updated:%s, upserted:%s)"% (
                move_count, r["modified_count"], r["upserted_count"]))
        else:
            logger.debug("no subnets updated for epg %s" % epg_dn)
        # ensure clear_cache sent to workers 
        # this needs to be done even if move count is zero since the 'src' bd
        # may not have any subnets but destination bd may have some present
        self.parent.clear_worker_cache("subnets_cache")

    def handle_subnet_event(self, e):
        """ receive event for fvSubnet or fvIpAttr and insert/delete/update
            corresponding entry in ep_subnets table
            classes:
                fvSubnet, fvIpAttr
            * fvSubnet can only be created/deleted, not modified
            * fvIpAttr can be created/deleted or modified. treat modify for
                fvIpAttr identical to created event
        """
        logger.debug("subnet_event: %s" % (ept_utils.pretty_print(e)))
       
        # parse required attributes from event 
        c = None
        attr = {}
        if "imdata" not in e or len(e["imdata"])==0: 
            logger.debug("invalid reply or empty data")
            return
        for event in e["imdata"]:
            c = event.keys()[0]
            if "attributes" in event[c]: attr = event[c]["attributes"]
            if "dn" not in attr or "status" not in attr:
                logger.warn("object missing dn or status: %s" % event)
                return
            break   # only one event should have occur
        if c is None:
            logger.warn("unable to determine class: %s" % e)
            return
        if c == "fvSubnet":
            parent_name = re.sub("/subnet-\[[^\]]+\]$", "", attr["dn"])
        elif c == "fvIpAttr":
            parent_name = re.sub("/crtrn/ipattr-.*", "", attr["dn"])
        else:
            logger.warn("invalid class %s for subnet_event" % c)
            return

        # map to bd_vnid for ep_subnets insert (note, if epg_name is actually
        # a bd, then the corresponding 
        bd_vnid = self.get_bd_vnid_for_dn(parent_name)
        if bd_vnid is None:
            logger.warn("failed to get bd_vnid for dn: %s" % parent_name)
            return

        # return only single subnet in subnets array that matches dn
        key = {"fabric":self.fabric,"subnets":{"$elemMatch":{"dn":attr["dn"]}}}
        with self.app.app_context():
            db = self.app.mongo.db
            h = db.ep_subnets.find_one(key)
            hs = None
            # set hs to subnet entry that matches dn
            if h is not None and "subnets" in h and len(h["subnets"])>0:
                hs = h["subnets"][0]
            # ensure current event is more recent than db entry
            if hs is not None and \
                ("ts" in hs and "_ts" in e and e["_ts"]<hs["ts"]):
                logger.debug("skipping %s, refresh not required (%s<%s)" % (
                    c, e["_ts"], hs["ts"]))
                return
            # handle deleted event
            if attr["status"] == "deleted":
                if h is not None:
                    logger.debug("deleting %s from subnets" % attr["dn"])
                    db.ep_subnets.update_one(key, 
                        {"$pull":{"subnets":{"dn":attr["dn"]}}})
                    self.parent.clear_worker_cache("subnets_cache")
                    return
                else:
                    logger.debug("ignoring delete for unknown subnet %s"%(
                        attr["dn"]))
                    return
            # handle created/modified event
            elif attr["status"] == "created" or attr["status"] == "modified":
                if attr["status"] == "modified" and c != "fvIpAttr":
                    logger.debug("skipping %s event for %s"%(attr["status"],c))
                    return
                if h is not None:
                    # if we get a create for a known subnet, delete first and
                    # then just reinsert it (always triggers a clear event)
                    logger.debug("deleting known subnet: %s"%attr["dn"])
                    db.ep_subnets.update_one(key, 
                        {"$pull":{"subnets":{"dn":attr["dn"]}}})
                if c == "fvIpAttr":
                    if "usefvSubnet" in attr and attr["usefvSubnet"]=="yes":
                        logger.debug("skipping fvIpAttr usefvSubnet: %s"%attr)
                        return
                # build subnet object
                subnet = parse_subnet_object(attr)
                if subnet is None:
                    logger.warn("failed to build subnet from %s" % attr)
                    return
                if "_ts" in e: subnet["ts"] = e["_ts"]
                else: subnet["ts"] = time.time()
                r1 = db.ep_subnets.update_one(
                    {"fabric": self.fabric, "vnid": bd_vnid},
                    {"$push":{"subnets":{"$each":[subnet]}}}, upsert=True)
                logger.debug("added subnet bd %s: %s" % (bd_vnid, subnet["ip"]))
                self.parent.clear_worker_cache("subnets_cache")
                return
            # no other event expected
            else:
                logger.warn("unexpected status %s for %s"%(attr["status"],c))
                return
            
    def get_bd_vnid_for_dn(self, dn):
        """ from particular dn, determine if it is bd or epg (fvAEPg or 
            vnsEPpInfo) dn and perform lookup into appropriate table to
            get bd_vnid value
                fvBD:
                    uni/tn-{name}/BD-{name}
                    uni/tn-{name}/svcBD-{name}
                fvAEPg: 
                    uni/tn-{name}/ap-{name}/epg-{name}
                vnsEPpInfo:
                    uni/tn-{name}/LDevInst-{[priKey]}-ctx-{ctxName}/
                        G-{graphRn}-N-{nodeRn}-C-{connRn}
                    uni/vDev-{[priKey]}-tn-{[tnDn]}-ctx-{ctxName}/rndrInfo/
                        eppContr/G-{graphRn}-N-{nodeRn}-C-{connRn}
            return None on error
        """
        table = None
        if "/BD-" in dn or "/svcBD-" in dn: table = "ep_vnids"
        else: table = "ep_epgs"
        logger.debug("mapping bd_vnid against table %s for dn: %s"%(table,dn))
        key = {"fabric":self.fabric, "name": dn}
        with self.app.app_context():
            db = self.app.mongo.db
            h = db[table].find_one(key)
            if h is None:
                logger.debug("failed to find dn %s" % dn)
                return None
            if table == "ep_vnids":
                logger.debug("dn: %s maps to bd_vnid: %s" % (dn, h["vnid"]))
                return h["vnid"]
            else:
                if "bd_vnid" not in h or len(h["bd_vnid"])==0:
                    logger.debug("bd_vnid not set for epg %s" % dn)
                    return None
                logger.debug("dn: %s maps to bd_vnid: %s" % (dn, h["bd_vnid"]))
                return h["bd_vnid"]

    def refresh_epg_bd_vnid(self, rsbd_dn, current_bd_vnid):
        """ refresh epg bd_vnid in ep_epgs table and if different from 
            provided current_bd_vnid
            return new bd_vnid if different else return None
        """
        js = ept_utils.get_dn(self.session, rsbd_dn) 
        if js is None: 
            logger.warn("failed to get rsbd_dn(%s)" % rsbd_dn)
            return None
        logger.debug("refreshed(%s): %s"%(rsbd_dn,js))
        if len(js) == 0: return None
        c = js.keys()[0]
        if "attributes" in js[c]:
            attr = js[c]["attributes"]
            if "tDn" not in attr or "dn" not in attr: 
                logger.warn("invalid %s object: %s" % (c, attr))
                return None
            epg_name = re.sub("/(rsbd|rsEPpInfoToBD)$", "", attr["dn"])
            bd_name = attr["tDn"]
            # database lookup to get bd_vnid for bd_name and then update
            key = {"fabric": self.fabric, "name": bd_name}
            with self.app.app_context():
                db = self.app.mongo.db
                h = db.ep_vnids.find_one(key)
                if h is None:
                    logger.warn("unable to map bd_vnid for bd: %s" % bd_name)
                    return None
                if h["vnid"] != current_bd_vnid:
                    logger.debug("updated bd_vnid for %s from '%s' to '%s'" % (
                        epg_name, current_bd_vnid, h["vnid"]))
                    return h["vnid"]
                else:
                    logger.debug("epg %s bd_vnid(%s) unchanged" % (epg_name, 
                        h["vnid"]))
        return None
                
    def refresh_session(self):
        """ update self.session object with fresh apic session
            force a hard reset if session refresh fails
        """
        ts = time.time()
        if self.last_session_refresh + self.session_refresh_time > ts:
            logger.debug("session refresh not required")
            self.last_session_refresh = ts
            return
        logger.debug("refreshing session")
        self.session = ept_utils.refresh_session(self.fabric, self.session)
        if self.session is None:
            logger.warn("failed to refresh apic session")
            self.hard_restart("failed to connect to APIC")
            return
        self.last_session_refresh = ts

def process_name_object(fabric, classname, attr):
    """ process provided classname and attributes and parse determine which 
        table needs to be updated/checked along with corresponding attributes:
            fvCtx, fvBD, l3extExtEncapAllocator, fvSvcBD
                ep_vnids: {fabric, vnid, vrf, name, pcTag, encap}
            fvEPg(fvAEPg, l3extInstP, vnsEPpInfo)
                ep_epgs: {fabric, vnid, name, pcTag, bd_vnid, isAttrBasedEPg}
        returns a dict with:{
            "table": "string table name"
            "key": key dictionary
            }
        return None on error
    """
    try:
        key = {"fabric":fabric, "name": attr["dn"], "vnid":"", "pcTag":""}
        if "pcTag" in attr:
            key["pcTag"] = attr["pcTag"]
        if classname == "fvAEPg" or classname == "l3extInstP" or \
            classname == "vnsEPpInfo" or classname == "mgmtInB" or \
            classname == "mgmt":
            table = "ep_epgs"
            key["vnid"] = attr["scope"]
            key["bd_vnid"] = ""
            key["isAttrBasedEPg"] = ""
            if "isAttrBasedEPg" in attr: 
                key["isAttrBasedEPg"] = attr["isAttrBasedEPg"]
        else:
            table = "ep_vnids"
            if classname == "fvBD" or classname == "fvSvcBD":
                key["vnid"] = attr["seg"]
                key["vrf"] = attr["scope"]
                key["encap"] = ""
            elif classname == "fvCtx":
                key["vnid"] = attr["scope"] 
                key["vrf"] = attr["scope"]
                key["encap"] = ""
            elif classname == "l3extExtEncapAllocator":
                key["vnid"] = re.sub("i?vx?lan-", "", attr["extEncap"])
                key["vrf"] = ""
                key["encap"] = attr["encap"]
            else:
                logger.warn("unknown classname %s" % classname)
                return None
        return {"table":table, "key":key}
    except KeyError as e:
        logger.warn("keyerror for key %s in %s: %s" %(e, classname, attr))
        return None

def parse_subnet_object(attr):
    """ process provided subnet object and return dict with attributes {
            "type": ipv4 or ipv6
            "addr"  integer address for prefix
            "mask": interge mask for prefix
            "ip":   prefix name as provided in original attribute
            "dn":   original dn for subnet/ip-attribute object
        }
        returns None on error
    """
    if "ip" not in attr or "dn" not in attr: 
        logger.warn("invalid %s object: %s" % (classname, attr))
        return None
    ret = {"type": "","addr":None,"mask":None,"ip":attr["ip"],"dn":attr["dn"]}
    if ":" in attr["ip"]:
        ret["type"] = "ipv6"
        (ret["addr"], ret["mask"]) = ept_utils.get_ipv6_prefix(attr["ip"])
    else:
        ret["type"] = "ipv4"
        (ret["addr"], ret["mask"]) = ept_utils.get_ipv4_prefix(attr["ip"])
        
    if ret["addr"] is None or ret["mask"] is None:
        logger.warn("failed to parse ip: %s" % ret["ip"])
        return None

    # always convert integer to string for database store
    ret["addr"] = "%s" % ret["addr"]
    ret["mask"] = "%s" % ret["mask"]
    return ret

def build_initial_tunnel_db(fabric, session, app):
    """ query tunnelIf class to build initial (hopefully stable) entries """
    ept_utils.setup_logger(logger, "%s_ep_worker_pri.log" % fabric)

    logger.debug("build_initial_tunnel_db start")
    start_ts = time.time()
    inserted_count = 0
    table = "ep_tunnels"
    bulk_updates = {table:[]}
    classname = "tunnelIf"

    js = ept_utils.get_class(session, classname)
    if js is None:
        logger.warn("failed to get tunnelIf data")
        return False
    logger.debug("build_initial_tunnel_db query time:%f" % (
        time.time()-start_ts))
       
    tunnelIf_fields = ["dn","dest","operSt","src","tType","type", "id"]
    node_reg = re.compile("/node-(?P<id>[0-9]+)/")
    with app.app_context():
        # first delete existing ep_tunnels database
        db = app.mongo.db
        db[table].delete_many({"fabric": "%s" % fabric})
        obj = []
        for node in js:
            #logger.debug("received %s: %s" % (classname, node))
            if classname in node and "attributes" in node[classname]:
                attr = node[classname]["attributes"]
                update = {}
                for r in tunnelIf_fields:
                    if r not in attr:
                        logger.warn("attribute %s missing from node" % r)
                        continue
                    update[r] = attr[r]
                # get node id from dn
                r1 = node_reg.search(attr["dn"])
                if r1 is None: 
                    logger.warn("unable to determine node from dn: %s"%dn)
                    continue
                # extract node-id from tunnelIf dn
                update["node"] = r1.group("id")
                if update["node"] is None: continue
                update["fabric"] = fabric

                # add to bulk_updates list
                bulk_updates[table].append(InsertOne(update))
                if len(bulk_updates[table])>ept_utils.MAX_BULK_SIZE:
                    r = ept_utils.bulk_update(table, bulk_updates,app=app)
                    inserted_count+= r["inserted_count"]

        # perform bulk update of all remaining objects
        r = ept_utils.bulk_update(table, bulk_updates, app=app)
        inserted_count+= r["inserted_count"]
        logger.debug("build_initial_tunnel_db time:%f,insert:%s" % (
            (time.time()-start_ts), inserted_count))
        return True

def build_initial_node_db(fabric, session, app):
    """ query topSystem class to build initial (hopefully stable) entries """
    ept_utils.setup_logger(logger, "%s_ep_worker_pri.log" % fabric)

    logger.debug("build_initial_node_db start")
    start_ts = time.time()
    inserted_count = 0
    table = "ep_nodes"
    bulk_updates = {table:[]}

    js = ept_utils.get_class(session, "topSystem")
    if js is None:
        logger.warn("failed to get topSystem data")
        return False
    logger.debug("build_initial_node_db query time:%f" % (
        time.time()-start_ts))
        
    with app.app_context():
        # first delete existing ep_node database
        db = app.mongo.db
        db.ep_nodes.delete_many({"fabric":"%s" % fabric})
        obj = []
        req = ("id", "state", "role", "systemUpTime",
                "address", "name", "dn", "podId", "oobMgmtAddr", "inbMgmtAddr")
        for node in js:
            #logger.debug("received node: %s"%ept_utils.pretty_print(node))
            if "topSystem" in node and "attributes" in node["topSystem"]:
                attr = node["topSystem"]["attributes"]
                update = {}
                update["fabric"] = fabric
                update["peer"] = "" # peer value built during vpc init
                invalid_obj = False
                for r in req:
                    if r not in attr:
                        logger.warn("attribute %s missing from node" % r)
                        invalid_obj = True
                        break
                    update[r] = attr[r]
                if invalid_obj: continue
                bulk_updates[table].append(InsertOne(update))
                if len(bulk_updates[table])>ept_utils.MAX_BULK_SIZE:
                    r = ept_utils.bulk_update(table, bulk_updates,app=app)
                    inserted_count+= r["inserted_count"]

        # perform bulk update of all remaining objects
        r = ept_utils.bulk_update(table, bulk_updates, app=app)
        inserted_count+= r["inserted_count"]
        logger.debug("build_initial_node_db time:%f,insert:%s" % (
            (time.time()-start_ts), inserted_count))
        return True

def build_vpc_node_db(fabric, session, app):
    """ query fabricNodePEp and parent classes to add vpc domains to ep_node"""
    ept_utils.setup_logger(logger, "%s_ep_worker_pri.log" % fabric)

    logger.debug("build_vpc_node_db start")
    start_ts = time.time()
    inserted_count = 0
    modified_count = 0
    table = "ep_nodes"
    query_count = 1
    bulk_updates = {table:[]}

    # two types of vpc pairs, auto or explicit
    # fabricAutoGEp = uni/fabric/protpol/autogep-group-101-103
    # fabricExplicitGEp = uni/fabric/protpol/expgep-vpc-domain-1
    with app.app_context():
        db = app.mongo.db
        js = None
        for vpcType in ("fabricExplicitGEp", "fabricAutoGEp"):
            tmp_ts = time.time()
            js = ept_utils.get_class(session, vpcType, 
                queryTarget="subtree",
                targetSubtreeClass="%s,fabricNodePEp" % vpcType)
            logger.debug("build_vpc_node_db query%s time:%f" % (
                query_count, time.time()-tmp_ts))
            query_count+= 1
            if js is None:
                logger.warn("failed to get class %s" % vpcType)
            elif len(js)==0:
                logger.debug("no vpc's of type %s" % vpcType)
            else:
                logger.debug("found vpc's of type %s" % vpcType)
                break
        if js is None or len(js)==0:
            logger.debug("no vpc configuration found")
            logger.debug("build_vpc_node_db time:%f,insert:%s,modify:%s" % (
                (time.time()-start_ts), inserted_count, modified_count))
            return True

        # build out logical vpc domain object and add to ep_node
        # format: {'id': 0x10000 + group-id, name: group-name, state: '',
        #   oobMgmtAddr:'', role:'vpc', systemUptime:'',
        #   address: group-virtualIp, nodes:[node-id-1, node-id-2]
        #   requires exactly 2 nodes 
        groups = {}
        # first loop to find groups
        for obj in js:
            logger.debug("%s object/child: %s" % (vpcType, 
                ept_utils.pretty_print(obj)))
            if vpcType in obj and "attributes" in obj[vpcType]:
                attr = obj[vpcType]["attributes"]
                t = {
                    "oobMgmtAddr": "", "inbMgmtAddr":"",
                    "role":"vpc", "systemUptime":"",
                    "nodes":{}, "state":""
                } 
                for r in ("virtualIp", "name", "id", "dn"):
                    if r not in attr:
                        logger.warn("attribute %s missing from %s"%(r,vpcType))
                        continue
                    t[r] = attr[r]
                t["address"] = re.sub("/[0-9]+","", t["virtualIp"]) #remove mask
                t.pop("virtualIp", None)
                groups[t["dn"]] = t

        # second loop to find member nodes
        oType = "fabricNodePEp"
        for node in js:
            if oType in node and "attributes" in node[oType]:
                attr = node[oType]["attributes"]
                if "dn" not in attr or "peerIp" not in attr:
                    logger.warn("attribute dn or peerIp missing: %s" % attr)
                    continue
                # get parent dn
                pdn = ept_utils.get_parent_dn(attr["dn"])
                if pdn in groups:
                    p = groups[pdn]
                    if attr["id"] not in p["nodes"]:
                        if len(p["nodes"])>=2:
                            logger.warn("can't add 3rd node(%s) to vpc(%s)"%(
                                attr, p))
                            continue
                        p["nodes"][attr["id"]] = {
                            "id": attr["id"],
                            "peerIp": re.sub("/[0-9]+$","", attr["peerIp"]),
                        }

        # now add any groups to database that have exactly 2 nodes configured
        updates = []
        per_node_updates = []
        for dn in groups:
            g = groups[dn]
            if len(g["nodes"]) == 2:
                # remap 'nodes' to a list (easier to work with for api)
                g["nodes"] = [g["nodes"][n] for n in g["nodes"]]
                # rewrite group id to (node1)<<16 + node2
                try:
                    n1 = g["nodes"][0]["id"]
                    n2 = g["nodes"][1]["id"]
                    vpc_node = get_vpc_domain_id(n1, n2)
                    g["id"] = "%s" % vpc_node
                    bulk_updates[table].append(UpdateOne({
                            "fabric": fabric,
                            "id": "%s" % n1
                        },{ "$set":{"peer":"%s" % n2}}))
                    bulk_updates[table].append(UpdateOne({
                            "fabric": fabric,
                            "id": "%s" % n2
                        },{ "$set":{"peer":"%s" % n1}}))
                except ValueError as e:
                    logger.error("invalid node id in group: %s" % g)
                    continue
                g["fabric"] = fabric
                bulk_updates[table].append(InsertOne(g))
                if len(bulk_updates[table])>ept_utils.MAX_BULK_SIZE:
                    r = ept_utils.bulk_update(table, bulk_updates,app=app)
                    inserted_count+= r["inserted_count"]
                    modified_count+= r["modified_count"]

        # perform bulk update of all remaining objects
        r = ept_utils.bulk_update(table, bulk_updates, app=app)
        inserted_count+= r["inserted_count"]
        modified_count+= r["modified_count"]
        logger.debug("build_vpc_node_db time:%f,insert:%s,modify:%s" % (
            (time.time()-start_ts), inserted_count, modified_count))
    return True

def build_vpc_config_db(fabric, session, app):
    """ query vpcRsVpcConf class to build initial ep_vpcs table """
    ept_utils.setup_logger(logger, "%s_ep_worker_pri.log" % fabric)

    logger.debug("build_vpc_config_db start")
    start_ts = time.time()
    inserted_count = 0
    table = "ep_vpcs"
    bulk_updates = {table:[]}

    js = ept_utils.get_class(session, "vpcRsVpcConf")
    if js is None:
        logger.warn("failed to get vpcRsVpcConf data")
        return False
    logger.debug("build_vpc_config_db query time:%f" % (
        time.time()-start_ts))
        
    reg = re.compile("node-(?P<node>[0-9]+)/sys/")
    with app.app_context():
        # first delete existing ep_vpcs database
        db = app.mongo.db
        db.ep_vpcs.delete_many({"fabric":"%s" % fabric})
        obj = []
        req = ("dn", "parentSKey", "tSKey")
        for entry in js:
            if "vpcRsVpcConf" in entry and \
            "attributes" in entry["vpcRsVpcConf"]:
                attr = entry["vpcRsVpcConf"]["attributes"]
                update = {}
                update["fabric"] = fabric
                invalid_obj = False
                for r in req:
                    if r not in attr:
                        logger.warn("attribute %s missing from node" % r)
                        invalid_obj = True
                        break
                if invalid_obj: continue
                # extract node from dn
                r1 = re.search(reg, attr["dn"])
                if r1 is None:
                    logger.warn("failed to extract node id from: %s"%attr["dn"])
                    continue
                bulk_updates[table].append(InsertOne({
                    "fabric": fabric,
                    "node": r1.group("node"),
                    "po": attr["tSKey"],
                    "vpc": attr["parentSKey"]
                }))
                if len(bulk_updates[table])>ept_utils.MAX_BULK_SIZE:
                    r = ept_utils.bulk_update(table, bulk_updates,app=app)
                    inserted_count+= r["inserted_count"]

        # perform bulk update of all remaining objects
        r = ept_utils.bulk_update(table, bulk_updates, app=app)
        inserted_count+= r["inserted_count"]
        logger.debug("build_vpc_config_db time:%f,insert:%s" % (
            (time.time()-start_ts), inserted_count))
        return True

def build_initial_name_db(fabric, session, app):
    """ query multiple objects to build ep_vnids and ep_epgs tables """
    ept_utils.setup_logger(logger, "%s_ep_worker_pri.log" % fabric)

    logger.debug("build_initial_name_db start")
    start_ts = time.time()
    inserted_count = 0
    query_count = 1
    bulk_updates = {"ep_vnids":[], "ep_epgs":[]}
 
    classes = ["fvCtx", "fvBD", "fvSvcBD", "fvEPg", "l3extExtEncapAllocator"]
    with app.app_context():
        db = app.mongo.db
        db.ep_vnids.delete_many({"fabric":"%s" % fabric})
        db.ep_epgs.delete_many({"fabric":"%s" % fabric})
        keys = {"ep_vnids":{}, "ep_epgs":{}} # track all keys to prevent dups
        for classname in classes:
            ts = time.time()
            js = ept_utils.get_class(session, classname)
            if js is None:
                logger.warn("failed to get %s data" % classname)
                return False
            logger.debug("build_initial_name_db query%s time:%f" % (
                query_count, time.time()-ts))
            query_count+=1
            for entry in js:
                c = entry.keys()[0]
                if c in entry and "attributes" in entry[c]:
                    attr = entry[c]["attributes"]
                    p = process_name_object(fabric, c, attr)
                    if p is None:
                        logger.warn("failed to process %s: %s" % (c, attr))
                        continue
                    if p["table"] not in bulk_updates:
                        logger.warn("unexpected bulk_update: %s"%p["table"])
                        continue
                    p["key"]["ts"] = ts
                    # ensure key is not duplicate entry in database
                    k = p["key"]["name"]
                    if k in keys[p["table"]]:
                        logger.warn("skipping duplicate key in %s: %s" % (
                            p["table"], k))
                    keys[p["table"]][k] = 1
                    logger.debug("adding to bulk %s:(%s)"%(p["table"],p["key"]))
                    bulk_updates[p["table"]].append(InsertOne(p["key"]))
                    if len(bulk_updates[p["table"]])>ept_utils.MAX_BULK_SIZE:
                        r = ept_utils.bulk_update(p["table"], bulk_updates,
                            app=app)
                        inserted_count+= r["inserted_count"]
                        
        # perform single write
        for table in bulk_updates:
            r = ept_utils.bulk_update(table, bulk_updates, app=app)
            inserted_count+= r["inserted_count"]
        logger.debug("build_initial_name_db time:%f,insert:%s" % (
            (time.time()-start_ts), inserted_count))
        return True

def build_initial_epg_to_bd_vnid_db(fabric, session, app):
    """ query fvRsBd to get epg to bd mapping and cross reference with existing
        ep_vnids table to determine bd vnid for each epg
        this MUST be done after build_initial_name_db has completed
    """
    ept_utils.setup_logger(logger, "%s_ep_worker_pri.log" % fabric)

    logger.debug("build_initial_epg_to_bd_vnid_db start")
    start_ts = time.time()
    inserted_count = 0
    query_count = 0
    table = "ep_epgs"
    bulk_updates = {table:[]}
    classes = ["fvRsBd", "vnsRsEPpInfoToBD", "mgmtRsMgmtBD"]

    bd_vnids = {} # all BD vnids indexed by BD name
    with app.app_context():
        db = app.mongo.db
        for vnid in db.ep_vnids.find({"fabric":fabric}):
            if "BD-" in vnid["name"]: bd_vnids[vnid["name"]] = vnid
        # get all fvRsBd objects and create mapping to BD vnid
        for classname in classes:
            query_count+=1
            ts = time.time()
            js = ept_utils.get_class(session, classname)
            if js is None:
                logger.warn("failed to get %s data" % classname)
                return False
            logger.debug("build_initial_epg_to_bd_vnid_db query%s time:%f" % (
                query_count, time.time()-ts))
            for entry in js:
                c = entry.keys()[0]
                if c in entry and "attributes" in entry[c]:
                    attr = entry[c]["attributes"]
                    if "tDn" not in attr or "dn" not in attr: 
                        logger.warn("invalid %s object: %s" % (c, attr))
                        continue
                    epg_name = re.sub("/(rsbd|rsEPpInfoToBD|rsmgmtBD)$", "", 
                        attr["dn"])
                    bd_name = attr["tDn"]
                    if bd_name not in bd_vnids:
                        logger.warn("failed to map epg %s, unknown BD: %s"%(
                            epg_name, bd_name))
                        continue
                    logger.debug("adding to bulk %s:(%s, bd_vnid:%s)" % (table,
                        epg_name,bd_vnids[bd_name]["vnid"]))
                    bulk_updates[table].append(UpdateOne(
                        {"fabric":fabric,"name":epg_name},
                        {"$set":{"bd_vnid":bd_vnids[bd_name]["vnid"]}},
                        upsert=True
                    ))
                    if len(bulk_updates[table])>ept_utils.MAX_BULK_SIZE:
                        r = ept_utils.bulk_update(table, bulk_updates, app=app)
                        inserted_count+=r["upserted_count"]+r["modified_count"]

        # perform single write of whatever's left in bulk_updates
        r = ept_utils.bulk_update(table, bulk_updates, app=app)
        inserted_count+=r["upserted_count"]+r["modified_count"]
        logger.debug("build_initial_epg_to_bd_vnid_db time:%f,insert:%s" % (
            (time.time()-start_ts), inserted_count))
        return True

def build_initial_subnets_db(fabric, session, app):
    """ query different objects with fvSubnet to build per-BD subnets
            - fvBD (fvSubnet)
            - fvAEPg (fvSubnet, fvIpAttr)
            - vnsEPpInfo (fvSubnet)
            - vnsLIfCtx (fvSubnet, vnsRsLIfCtxToBD) 
                * this appears to be duplicate of vnsEPpInfo and since pcTag
                  is assigned to vnsEPpInfo, if the ip is learned is *should*
                  come with vnsEPpInfo
                  for now, let's ignore it...
        this MUST be done after build_initial_epg_to_bd_vnid_db completed
    """

    logger.debug("build_initial_subnets_db start")
    start_ts = time.time()
    subnet_count = 0
    query_count = 0
    ep_subnets = {} # indexed by bd_vnid
    bulk_updates = {"ep_subnets":[]}

    bd_vnids = {} # all BD vnids indexed by BD name
    epg_vnids = {} # all epg vnids indexed by EPG name
    with app.app_context():
        db = app.mongo.db
        db.ep_subnets.delete_many({"fabric":"%s" % fabric})
        for vnid in db.ep_vnids.find({"fabric":fabric}):
            if "BD-" in vnid["name"]: bd_vnids[vnid["name"]] = vnid
        for epg in db.ep_epgs.find({"fabric":fabric}):
            epg_vnids[epg["name"]] = epg

        # handle fvBD subnets
        classname = "fvBD"
        query_count+=1
        ts = time.time()
        js = ept_utils.get_class(session, classname, queryTarget="children",
            targetSubtreeClass="fvSubnet")
        if js is None:
            logger.warn("failed to get %s data" % classname)
            return False
        logger.debug("build_initial_subnets_db query%s time:%f" %(query_count, 
            time.time()-ts))
        for entry in js:
            c = entry.keys()[0]
            if c in entry and "attributes" in entry[c]:
                attr = entry[c]["attributes"]
                bd_name = re.sub("/subnet-\[[^\]]+\]$", "", attr["dn"])
                if bd_name not in bd_vnids:
                    logger.warn("unable to map bd for %s" % attr["dn"])
                    continue
                bd_vnid = bd_vnids[bd_name]["vnid"]
                subnet = parse_subnet_object(attr)
                subnet["ts"] = ts
                if subnet is None:
                    logger.warn("invalid subnet object: %s" % attr)
                    continue
                if bd_vnid not in ep_subnets: 
                    ep_subnets[bd_vnid] = {"fabric":fabric, "vnid":bd_vnid,
                        "subnets":[]}
                logger.debug("adding %s to bd: %s" % (subnet["ip"], bd_vnid))
                ep_subnets[bd_vnid]["subnets"].append(subnet)
                subnet_count+=1

        # handle fvAEPg/vnsEPpInfo the same (subnets and useg IP attributes)
        classnames = ["fvAEPg", "vnsEPpInfo"]
        for classname in classnames:
            query_count+=1
            ts = time.time()
            js = ept_utils.get_class(session, classname, queryTarget="subtree",
                targetSubtreeClass="fvSubnet,fvIpAttr")
            if js is None:
                logger.warn("failed to get %s data" % classname)
                return False
            logger.debug("build_initial_subnets_db query%s time:%f" %(
                query_count, time.time()-ts))
            for entry in js:
                c = entry.keys()[0]
                if c in entry and "attributes" in entry[c]:
                    attr = entry[c]["attributes"]
                    if c == "fvSubnet":
                        epg_name = re.sub("/subnet-\[[^\]]+\]$", "", attr["dn"])
                    elif c == "fvIpAttr":
                        if "usefvSubnet" in attr and attr["usefvSubnet"]=="yes":
                            logger.debug("skipping fvIpAttr usefvSubnet: %s"%(
                                attr))
                            continue
                        epg_name = re.sub("/crtrn/ipattr-.*", "", attr["dn"])
                    else: continue
                    if epg_name not in epg_vnids or \
                        "bd_vnid" not in epg_vnids[epg_name] or \
                        len(epg_vnids[epg_name]["bd_vnid"]) == 0:
                        logger.warn("unable to map bd for %s" % attr["dn"])
                        continue
                    bd_vnid = epg_vnids[epg_name]["bd_vnid"]
                    subnet = parse_subnet_object(attr)
                    subnet["ts"] = ts
                    if subnet is None:
                        logger.warn("invalid subnet object: %s" % attr)
                        continue
                    if bd_vnid not in ep_subnets: 
                        ep_subnets[bd_vnid] = {"fabric":fabric, "vnid":bd_vnid,
                            "subnets":[]}
                    logger.debug("adding %s to bd: %s"%(subnet["ip"],bd_vnid))
                    ep_subnets[bd_vnid]["subnets"].append(subnet)
                    subnet_count+=1

        # handle vnsLIfCtx (fvSubnet, vnsRsLIfCtxToBD) --- ignore for now
        if False:
            classname = "vnsLIfCtx"
            query_count+=1
            ts = time.time()
            js = ept_utils.get_class(session, classname, queryTarget="children",
                targetSubtreeClass="fvSubnet,vnsRsLIfCtxToBD")
            if js is None:
                logger.warn("failed to get %s data" % classname)
                return False
            logger.debug("build_initial_subnets_db query%s time:%f"%(
                query_count, time.time()-ts))
            # first loop to build vnsLIfCtx to bd_vnid map via vnsRsLIfCtxToBD
            vns_vnids = {}
            for entry in js:
                c = entry.keys()[0]
                if c == "vnsRsLIfCtxToBD" and "attributes" in entry[c]:
                    attr = entry[c]["attributes"]
                    if "dn" not in attr or "tDn" not in attr:
                        logger.warn("invalid %s object: %s" % (c, attr))
                        continue
                    vns_name = re.sub("/rsLIfCtxToBD$","",attr["dn"])
                    bd_name = attr["tDn"]
                    if bd_name not in bd_vnids:
                        logger.warn("unable to map bd %s, %s" % (
                            bd_name,vns_name))
                        continue
                    vns_vnids[vns_name] = bd_vnids[bd_name]
            # second loop to add fvSubnet to ep_subnets
            for entry in js:
                c = entry.keys()[0]
                if c == "fvSubnet" and "attributes" in entry[c]:
                    attr = entry[c]["attributes"]
                    vns_name = re.sub("/subnet-\[[^\]]+\]$", "", attr["dn"])
                    if vns_name not in vns_vnids:
                        logger.warn("unknown vnsLIfCtx: %s" % attr["dn"])
                        continue
                    bd_vnid = vns_vnids[vns_name]["vnid"]
                    subnet = parse_subnet_object(attr)
                    subnet["ts"] = ts
                    if subnet is None:
                        logger.warn("invalid subnet object: %s" % attr)
                        continue
                    if bd_vnid not in ep_subnets: 
                        ep_subnets[bd_vnid] = {"fabric":fabric, "vnid":bd_vnid,
                            "subnets":[]}
                    logger.debug("adding %s to bd: %s" %(subnet["ip"],bd_vnid))
                    ep_subnets[bd_vnid]["subnets"].append(subnet)
                    subnet_count+=1

        # use bulk_update to add all ep_subnets to table
        for bd_vnid in ep_subnets:
            bulk_updates["ep_subnets"].append(InsertOne(ep_subnets[bd_vnid]))
        r = ept_utils.bulk_update("ep_subnets", bulk_updates,app=app)
        logger.debug("build_initial_subnets_db time:%f,insert:%s,subnets:%s" % (
            (time.time()-start_ts), r["inserted_count"],subnet_count))
        return True

def get_vpc_domain_id(n1, n2):
    """ calculate INTEGER vpc_id for two nodes """
    n1 = int(n1)
    n2 = int(n2)
    if n1>n2: vpc_node = (n1<<16) + n2
    else: vpc_node = (n2<<16) + n1
    return vpc_node

def get_nodes_from_vpc_id(vpc_id):
    """ calculate node-ids from vpc_id.  If not a vpc_id, then single node
        returned
    """
    try: vpc_id = int(vpc_id)
    except ValueError as e: return ["%s" % vpc_id ]
    if vpc_id > 0xffff:
        n1 = (0xffff0000 & vpc_id) >> 16
        n2 = (0x0000ffff & vpc_id)
        return ["%s" % n1, "%s" % n2]
    return ["%s" % vpc_id]

def get_node_string(node):
    """ returns string for node or vpc pair of nodes """
    try: node = int(node)
    except ValueError as e: return "%s" % node
    if node > 0xffff:
        n1 = (node>>16) & 0xffff
        n2 = node & 0xffff
        if n1 > n2: 
            return "(%s,%s)" % (n2,n1)
        return "(%s,%s)" % (n1,n2)
    elif node == 0:
        # when 'expected' node not found, we set to value of zero
        # therefore, 0 is reserved value for 'deleted' 
        return "deleted"
    else:
        return "%s" % node
        
