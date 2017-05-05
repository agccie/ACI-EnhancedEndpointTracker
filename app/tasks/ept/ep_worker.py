"""
    Endpoint Worker
    @author agossett@cisco.com
"""

from . import utils as ept_utils
from .node_manager import (get_vpc_domain_id, get_node_string, 
                           get_nodes_from_vpc_id)
from .ep_job import EPJob
from Queue import Empty
import time, traceback, copy, re

# setup logger for this package
import logging
logger = logging.getLogger(__name__)
ept_utils.setup_logger(logger)

# various epm merge/move/change attributes
epm_change_fields =["flags","ifId","pcTag","bd","vrf","encap","remote",
                    "rw_bd","rw_mac"]
epm_sub1_change_fields = ["flags","ifId","pcTag","bd","vrf","encap","remote"]
epm_sub2_change_fields = ["rw_bd", "rw_mac"]
epm_rs_merge_fields=["bd", "vrf", "pcTag", "flags", "encap", "ifId", "remote",
                     "dn", "epg_name", "vnid_name"]
epm_move_fields = ["node", "ifId", "encap", "pcTag", "rw_bd", "rw_mac"]

class EPWorker(object):
    """ perform endpoint monitoring task """

    def __init__(self, txQ, rxQ, prQ, fabric, overlay_vnid, wid):
        self.txQ = txQ
        self.rxQ = rxQ
        self.prQ = prQ
        self.fabric = fabric
        self.overlay_vnid = overlay_vnid
        self.wid = wid
        # setup logging for this fabric
        ept_utils.setup_logger(logger, "%s_ep_worker_%s.log" % (
            self.fabric, self.wid), quiet=True)
        ept_utils.logger = logger
        self.app = ept_utils.get_app()
        self.session = None
        self.tunnel_cache = {}  # cache of tunnel to remote node
        self.node_cache = {}    # cache of vpc peer node id's
        self.pc_cache = {}      # cache of port-channel to vpc-id peer node
        self.vnids_cache = {}   # cache of vnid to name mapping
        self.epgs_cache = {}    # cache of epg (vnid+pcTag) to name mapping
        self.subnets_cache = {} # cache of epg (vnid+pcTag) to subnets mapping
        self.hit_cache = {}     # object for tracking last hits to above caches
                                # along with cleaning up old entries
        self.max_cache_size = 512

        # trust subscription flag to determine whether each event requires 
        # ep_refresh or if event can be inserted directly into database
        # this flag is ep_subscriber when worker is started
        self.trust_subscription = True

        # further anaylsis stale endpoints to ensure event is not transistory
        self.stale_double_check = True
        self.offsubnet_double_check = True

        # per-fabric config with defaults overwritten by setter
        self.max_ep_events = 64
        self.analyze_move = True 
        self.analyze_stale = True 
        self.analyze_offsubnet = True 
        self.auto_clear_stale = False 
        self.auto_clear_offsubnet = False 
        self.notify_stale_syslog = False 
        self.notify_stale_email = False 
        self.notify_move_syslog = False 
        self.notify_move_email = False 
        self.notify_offsubnet_syslog = False 
        self.notify_offsubnet_email = False 
        self.notify_email = ""          # email address to send notifications
        self.notify_syslog = ""         # syslog server to send notifications
        self.notify_syslog_port = 514 
        self.worker_hello = 3.0          # worker hello ping interval
        self.worker_hello_multiplier = 4 # max amount of hellos to miss

        # last read used between ep_analyze_move and ep_analyze_stale
        self.last_db_read_key = None
        self.last_db_read_value = None

        # job handlers and corresponding functions to execute. Update this 
        # object instead of modify the start function directly...
        self.job_handlers = {
            "ep_analyze": self.ep_analyze,
            "ep_notify_fail": self.ep_notify_fail,
            "setter": self.setter,
            "clear_cache": self.clear_cache,
            "watch_node": self.watch_node,
            "watch_stale": self.watch_event,
            "watch_offsubnet": self.watch_event,
        }

        # dict of watched jobs indexed by job key where job.ts is timestamp
        # to re-execute the job (at best queue_interval accuracy)
        self.watched = {}       

        # various intervals used by subscription and/or workers
        self.queue_interval = 0.1   
        self.transitory_delete_time = 3.0  
        self.transitory_stale_time = 30.0
        # only alert stale for XR if still present after XR aging time 
        # (default of 300 seconds) 
        self.transitory_xr_stale_time = 300.0 
        self.transitory_offsubnet_time = 30.0

    def __repr__(self):
        return "%s:w%s" % (self.fabric, self.wid)

    def start(self):
        """ start listening on queue for jobs, put completed job object on
            txQ so parent knows it has completed
        """
        logger.debug("[%s] now listening for jobs (queue_interval:%f)" % (
            self, self.queue_interval))
        while True:
            job = None
            watching = False
            while job is None and not watching:
                # process all messages from prQ before checking rxQ
                try: job = self.prQ.get_nowait()
                except Empty:
                    try: job = self.rxQ.get_nowait()
                    except Empty:
                        watching = len(self.watched)>0
                        if not watching: time.sleep(self.queue_interval)

            # job may be None and 'wakeup' triggered by non-zero watched dict
            if job is not None:
                # it's possible calling function may corrupt job keys, 
                # well create a duplicate job to ensure return process is 
                # always successful (additional sanity check only...)
                njob = EPJob(job.action, copy.copy(job.key))
                try:
                    # no action for hello, just put completed job back on queue
                    if job.action == "hello":  pass
                    else:
                        logger.debug("[%s] got job %s [prQ:%s,rxQ:%s]" % (
                            self,job,self.prQ.qsize(),self.rxQ.qsize()))
                        if job.action in self.job_handlers:
                            self.job_handlers[job.action](job)
                        else:
                            logger.error("[%s] unknown job action %s"%(self,
                                job))
                except Exception as e:
                    logger.error(traceback.format_exc())
                # always put completed/failed job back on parent queue
                self.txQ.put(njob)
                try:
                    if job.action!="hello":
                        logger.debug("[%s] finished job %s [prQ:%s,rxQ:%s]" % (
                            self,job,self.prQ.qsize(),self.rxQ.qsize()))
                except Exception as e: pass

            try:
                # check watched objects for any callbacks
                ts = time.time()
                push_back = []
                while len(self.watched)>0:
                    key,job = self.watched.popitem()
                    if job.execute_ts is None:
                        logger.warn("[%s] skipping job with bad ts: %s" % (
                            self, job))
                    elif ts >= job.execute_ts:
                        logger.debug("[%s] (total:%s) callback for %s" % ( 
                            self, len(self.watched), job))
                        if job.action in self.job_handlers:
                            self.job_handlers[job.action](job)
                            break
                    else: push_back.append((key,job))
                for t in push_back: self.watched[t[0]] = t[1]
            except Exception as e:
                logger.error(traceback.format_exc())
                raise e

    def setter(self, job):
        """ since worker is running as child process, we need a way for parent
            to update/set variables on this child process.  Since we already 
            have queuing process available, easiest way is to update setting
            via 'setter' job.  This function receives a dictionary 'data' with
            attributes of this object to update
        """
        data = job.data
        logger.debug("[%s] setter: %s" % (self, data))
        try:
            for k in data:
                # allow any local variable to be updated...
                if not hasattr(self, k):
                    logger.debug("[%s] ignoring update for attribute: %s" % (
                        self,k))
                else:
                    setattr(self, k, data[k])
            if "queue_interval" in data:
                logger.debug("[%s] queue_interval updated to: %f" % (
                    self, self.queue_interval))
        except Exception as e:
            logger.error(traceback.format_exc()) 
            return

    def extend_hello(self, time=0):
        """ send request to parent to temporarily extend the hello time 
            the extended time is max timeout + requested time
        """
        time = float(time) + self.worker_hello*self.worker_hello_multiplier
        self.txQ.put(EPJob("extend_hello", {}, data= {"time": time}))

    def requeue_job(self, jobs):
        """ send requeue job with list of jobs to be requeue to parent """
        # allow calling function to provide single job or list of jobs
        if isinstance(jobs, EPJob): jobs = [jobs]
        logger.debug("sending requeue job: %s" % jobs)
        self.txQ.put(EPJob("requeue", {}, data={"jobs":jobs}))

    def hit(self, cache_name, cache, key):
        """ ensure only the most recently used keys are kept in provided cache
            older keys will be removed once length of cache exceeds max size.
            This is done by maintaining a list of last_hit keys where the most
            recent key is pushed to the beginning of the list.
            
            cache_name - unique name of cache
            cache - cache dictionary
            key - most recently hit key, can provide a list of keys for nested
                  caches
        """
        delim = ":&?:"
        if type(key) is not list: key = [key]
        keystr = delim.join(key)
        if cache_name not in self.hit_cache: self.hit_cache[cache_name] = []
        if keystr in self.hit_cache[cache_name]:
            self.hit_cache[cache_name].remove(keystr)
        self.hit_cache[cache_name].insert(0, keystr)
        if len(self.hit_cache[cache_name])> self.max_cache_size:
            old = self.hit_cache[cache_name].pop().split(delim)
            # only support 3 level cache for now
            if len(old) == 3 and old[0] in cache and old[1] in cache[old[0]]:
                cache[old[0]][old[1]].pop(old[2], None)
                if len(cache[old[0]][old[1]])==0: 
                    cache[old[0]].pop(old[1],None)
                if len(cache[old[0]])==0:
                    cache.pop(old[0])
            elif len(old) == 2 and old[0] in cache:
                cache[old[0]].pop(old[1], None)
                if len(cache[old[0]])==0:
                    cache.pop(old[0])
            elif len(old) == 1:
                cache.pop(old[0], None)

    def clear_cache(self, job):
        """ clear cache provided in dict {"cache": "cache_name"} """
        data = job.data
        if "cache" not in data:
            logger.warn("invalid clear_cache data provided: %s" % data)
            return
        cache = data["cache"]
        if cache == "tunnel_cache":
            self.tunnel_cache = {}
            self.hit_cache.pop("tunnel", None)
        elif cache == "node_cache":
            self.node_cache = {}
            self.hit_cache.pop("node", None)
        elif cache == "pc_cache":
            self.pc_cache = {}
            self.hit_cache.pop("pc", None)
        elif cache == "vnids_cache":
            self.vnids_cache = {}
            self.hit_cache.pop("vnids", None)
        elif cache == "epgs_cache":
            self.epgs_cache = {}
            self.hit_cache.pop("epgs", None)
        elif cache == "subnets_cache":
            self.subnets_cache = {}
            self.hit_cache.pop("subnets", None)
        else:
            logger.warn("failed to clear unknown cache: %s" % cache)
            return
        logger.debug("cleared cache %s" % cache)

    def get_remote_node(self, node_id, tunnelIf):
        """ get_remote_node
            return node_id corresponding to provided (node_Id,tunnelIf) 
            None on error
        """
        # only perform lookup for tunnel interfaces
        if "tunnel" not in tunnelIf.lower(): return None

        # check if remote node has already been mapped
        if node_id in self.tunnel_cache and \
            tunnelIf in self.tunnel_cache[node_id]:
            self.hit("tunnel", self.tunnel_cache, [node_id, tunnelIf])
            return self.tunnel_cache[node_id][tunnelIf]

        # always create cache mapping
        if node_id not in self.tunnel_cache: self.tunnel_cache[node_id]={}
        self.tunnel_cache[node_id][tunnelIf] = None
        self.hit("tunnel", self.tunnel_cache, [node_id, tunnelIf])

        with self.app.app_context():
            # two lookups required, first to map tunnelIf to dstIP
            db = self.app.mongo.db
            dst = db.ep_tunnels.find_one({"fabric": self.fabric,
                "node":node_id, "id":tunnelIf})
            if dst is None or "dest" not in dst:
                logger.warn("destination not found in ep_tunnel(%s,%s)" % (
                        node_id,tunnelIf))
                return None
            # second lookup to map dstIp to remote node
            node = db.ep_nodes.find_one({"fabric": self.fabric, 
                "address":dst["dest"]})
            if node is None or "id" not in node:
                logger.warn("id not found in ep_nodes(address:%s)"%dst["dest"])
                return None

            # add entry to cache
            logger.debug("mapping %s:%s to %s"%(node_id,tunnelIf,node["id"]))
            self.tunnel_cache[node_id][tunnelIf] = node["id"]
            # return destination node
            return self.tunnel_cache[node_id][tunnelIf]

    def get_peer_node(self, node_id):
        """ get_peer_node
            return node_id of vpc peer for node.  
            None returned on error or if node is not in vpc
        """
        if node_id in self.node_cache:
            self.hit("node", self.node_cache, node_id)
            return self.node_cache[node_id]
    
        # always add entry to cache to prevent duplicate lookup
        self.node_cache[node_id] = None
        self.hit("node", self.node_cache, node_id)

        with self.app.app_context():
            db = self.app.mongo.db
            db_key = {"fabric":self.fabric, "id":node_id }
            n = db.ep_nodes.find_one(db_key)
            if n is None or "id" not in n:
                logger.warn("node id not found in ep_nodes(%s)"%node_id)
            elif "peer" in n and len(n["peer"])>0:
                self.node_cache[node_id] = n["peer"]
                # safe to assume that reverse mapping should always be present
                if n["peer"] not in self.node_cache:
                    self.node_cache[n["peer"]] = node_id
                    self.hit("node", self.node_cache, n["peer"])

        return self.node_cache[node_id]

    def get_vpc_from_pc(self, node_id, po):
        """ get vpc number from port-channel. 
            Return None on error (including if no mapping exists)
        """
        # only perform lookup for true port-channel interfaces
        if "po" not in po.lower(): return None
        if node_id in self.pc_cache and po in self.pc_cache[node_id]:
            self.hit("pc", self.pc_cache, [node_id, po])
            return self.pc_cache[node_id][po]

        # always add entry to cache to prevent duplicate lookup
        if node_id not in self.pc_cache: self.pc_cache[node_id] = {}
        self.hit("pc", self.pc_cache, [node_id, po])

        with self.app.app_context():
            db = self.app.mongo.db
            db_key = {"fabric":self.fabric, "node":node_id, "po":po}
            n = db.ep_vpcs.find_one(db_key)
            if n is None or "vpc" not in n:
                logger.warn("port-channel not found: %s" % db_key)
                self.pc_cache[node_id][po] = None
            else:
                self.pc_cache[node_id][po] = "vpc-%s" % n["vpc"]

        return self.pc_cache[node_id][po]

    def get_vnid_name(self, vnid, pcTag=None):
        """ get vnid name from ep_vnids table.  If pcTag is provided, also
            determine corresponding epg name with lookup on vrf vnid
            Returns dict: {vnid_name: "", epg_name: ""}
            returns None on error
        """
        #logger.debug("get vnid name (%s, %s)" % (vnid, pcTag))
        ret = {"vnid_name":None, "epg_name":None}
        if vnid in self.vnids_cache:
            self.hit("vnids", self.vnids_cache, vnid)
            ret["vnid_name"] = self.vnids_cache[vnid]
        if pcTag is not None and vnid in self.epgs_cache and \
            pcTag in self.epgs_cache[vnid]:
            self.hit("epgs", self.epgs_cache, [vnid, pcTag])
            ret["epg_name"] = self.epgs_cache[vnid][pcTag]
        if ret["vnid_name"] is not None and ret["epg_name"] is not None:
            #logger.debug("returning from cache: %s" % ret)
            return ret

        with self.app.app_context():
            db = self.app.mongo.db
            db_key = {"fabric": self.fabric, "vnid": vnid}
            vrf_vnid = None
            # need to do query if either vnid or epg mapping is missing as
            # epg needs 'vrf' mapping from vnid for l2 endpoints
            if ret["vnid_name"] is None or ret["epg_name"] is None:
                n = db.ep_vnids.find_one(db_key)
                if n is None or "name" not in n:
                    logger.debug("unable to map vnid name from key: %s"%db_key)
                else:
                    self.vnids_cache[vnid] = n["name"]
                    ret["vnid_name"] = n["name"]
                    self.hit("vnids", self.vnids_cache, vnid)
                    vrf_vnid = n["vrf"]
            if ret["epg_name"] is None and vrf_vnid is not None and \
                pcTag is not None and len(pcTag)>0 and pcTag!="any":
                db_key["pcTag"] = pcTag
                db_key["vnid"] = vrf_vnid
                n = db.ep_epgs.find_one(db_key)
                if n is None or "name" not in n:
                    logger.debug("unable to map epg name from key: %s"%db_key)
                else:
                    if vnid not in self.epgs_cache: self.epgs_cache[vnid]={}
                    self.epgs_cache[vnid][pcTag] = n["name"]
                    ret["epg_name"] = n["name"]
                    self.hit("epgs", self.epgs_cache, [vnid, pcTag])

        # add empty results to cache as well, cache cleared when db is updated
        if ret["vnid_name"] is None: 
            ret["vnid_name"] = ""
            self.vnids_cache[vnid] = ""
            self.hit("vnids", self.vnids_cache, vnid)
        if ret["epg_name"] is None and pcTag is not None:
            ret["epg_name"] = ""
            if vnid not in self.epgs_cache: self.epgs_cache[vnid] = {}
            self.epgs_cache[vnid][pcTag] = ""
            self.hit("epgs", self.epgs_cache, [vnid, pcTag])
        return ret

    def ep_is_offsubnet(self, vnid, addr, pcTag):
        """ receives (vrf)vnid, (ip)addr, and pcTag and returns True if ep is
            learned outside of configured subnets, else returns False
            returns None on error
        """
        # check for cache hit against vnid, pcTag, addr
        if vnid in self.subnets_cache and pcTag in self.subnets_cache[vnid] \
            and addr in self.subnets_cache[vnid][pcTag]:
            self.hit("subnets", self.subnets_cache, [vnid, pcTag, addr])
            logger.debug("(from cache) ep %s on %s,%s is_offsubnet: %r" % (
                addr, vnid, pcTag, self.subnets_cache[vnid][pcTag][addr]))
            return self.subnets_cache[vnid][pcTag][addr]

        # not currently in cache, first map (vnid/pcTag) to list of subnets
        if vnid not in self.subnets_cache or \
            pcTag not in self.subnets_cache[vnid]:
            if vnid not in self.subnets_cache: self.subnets_cache[vnid] = {}
            self.subnets_cache[vnid][pcTag] = {}
            self.subnets_cache[vnid][pcTag]["subnets"] = None
            logger.debug("perform db lookup for %s,%s subnets" % (vnid,pcTag))
            # need to get bd_vnid for epg(vnid/pcTag) from ep_epgs table
            with self.app.app_context():
                db = self.app.mongo.db
                db_key = {"fabric":self.fabric,"vnid":vnid,"pcTag":pcTag}
                n = db.ep_epgs.find_one(db_key)
                if n is None:
                    logger.debug("unable to map bd_vnid from key:%s" % db_key)
                elif "bd_vnid" not in n or len(n["bd_vnid"])==0:
                    logger.debug("no bd_vnid found for key:%s (%s)"%(db_key,n))
                else:
                    # second lookup to get subnet list for bd_vnid
                    db_subnets = db.ep_subnets.find_one({"fabric":self.fabric,
                        "vnid":n["bd_vnid"]})
                    if db_subnets is None or "subnets" not in db_subnets:
                        # no subnets configured under the bd, set to empty list
                        logger.debug("no subnets found for bd_vnid: %s" % (
                            n["bd_vnid"]))
                        subnets = []
                    else: 
                        # subnets addr/mask are stored as strings, we need to
                        # convert to int and to save mem, only store addr/mask
                        subnets = []
                        for s in db_subnets["subnets"]:
                            subnets.append({ "type": s["type"], "ip":s["ip"],
                                "addr":int(s["addr"]), "mask":int(s["mask"])})
                            logger.debug("adding subnet:%s to bd:%s" %(s["ip"],
                                n["bd_vnid"]))
                        self.subnets_cache[vnid][pcTag]["subnets"] = subnets

        # add the subnets to cache to save db lookups
        self.hit("subnets", self.subnets_cache, [vnid, pcTag])
        subnets = self.subnets_cache[vnid][pcTag]["subnets"]
        if subnets is None:
            logger.warn("failed to get subnet list for %s,%s"%(vnid,pcTag))
            ret = None
        else:
            addr_type = "ipv6" if ":" in addr else "ipv4"
            if addr_type == "ipv4": 
                (addr_addr, addr_mask) = ept_utils.get_ipv4_prefix(addr)
            else:
                (addr_addr, addr_mask) = ept_utils.get_ipv6_prefix(addr)
            if addr_addr is None or addr_mask is None:
                logger.warn("invalid ipv4/ipv6 address: %s" % addr)
                ret = None
            else:
                ret = True  # assume currently offsubnet unless we match
                for s in subnets:
                    logger.debug("checking against subnet:%s" %(s["ip"]))
                    if addr_type == s["type"] and \
                        s["addr"] == addr_addr & s["mask"]:
                        logger.debug("ep %s in %s:%s matches: 0x%x/0x%x"%(
                            addr, vnid, pcTag, s["addr"], s["mask"]))
                        ret = False
                        break
                if ret: 
                    logger.debug("ep %s on %s,%s does not match any subnet"%(
                        addr, vnid, pcTag))
                
        # add result to cache and return value
        self.hit("subnets", self.subnets_cache, [vnid, pcTag, addr])   
        self.subnets_cache[vnid][pcTag][addr] = ret
        return self.subnets_cache[vnid][pcTag][addr]
        
    def ep_analyze(self, job):
        """ two modes of operation:
            (1) trust_subscription enabled
                - send received event to ep_handle_event which returns whether
                an update occurred and if analyze is required
                - if analyze is required (and enabled) then call analysis for
                ep_analyze_move, ep_analyze_stale, ep_analyze_offsubnet
                - if analysis returns an update, perform proper notify function
                  or requeue further analysis job to parent
            (2) trust_subscription disabled
                - ignore received event and perform ep_refresh.  
                - if ep_refresh results in update, then call analysis for
                ep_analyze_move, ep_analyze_stale, ep_analyze_offsubnet
                - if analysis returns an update, perform proper notify function
        """
        # extract key/event from job
        key = job.key
        event = job.data

        # determine if an update has occurred
        if self.trust_subscription:
            (update, analyze) = self.ep_handle_event(event)            
            if not analyze: return
        else:
            (update, analyze) = self.ep_refresh(key, event_ts=job.ts)
            if not analyze: return

        # always clear last_db_read values before analyze
        self.last_db_read_key = None
        self.last_db_read_value = None

        # perform move analysis if enabled
        if not self.analyze_move:
            logger.debug("skipping move analysis for endpoint: %s" % key)
        else:
            updates = self.ep_analyze_move(key)
            if updates is None:
                logger.warn("failed to analyze move for endpoint: %s" % key)
            elif len(updates)>0: 
                self.ep_notify_move(key, updates)

        # perform stale analysis if enabled
        if not self.analyze_stale:
            logger.debug("skipping stale analysis for endpoint: %s" % key)
        else:
            updates = self.ep_analyze_stale(key)
            if updates is None: 
                logger.warn("failed to analyze stale endpoint: %s" % key)
            elif len(updates)>0: 
                ckey = copy.copy(key)
                if self.stale_double_check:
                    self.requeue_job(EPJob("watch_stale",ckey,data=updates))
                else:
                    # perform separate update for each stale entry
                    for node in updates:
                        ckey["node"] = node
                        self.ep_notify_stale(ckey, updates[node])

        # perform offsubnet analysis if enabled
        if not self.analyze_offsubnet:
            logger.debug("skipping offsubnet analysis for endpoint: %s" % key)
        else:
            updates = self.ep_analyze_offsubnet(key)
            if updates is None: 
                logger.warn("failed to analyze offsubnet endpoint: %s" % key)
            elif len(updates)>0: 
                ckey = copy.copy(key)
                if self.offsubnet_double_check:
                    self.requeue_job(EPJob("watch_offsubnet",ckey,data=updates))
                else:
                    # perform separate update for each offsubnet entry
                    for node in updates:
                        ckey["node"] = node
                        self.ep_notify_offsubnet(ckey, updates[node])

    def ep_handle_event(self, event):
        """ receives epm event from subscriber and inserts into database
            if different from previous event.
            event is result of parse_epm_event
                        
            return tuple of two booleans where:
                tuple[0] = update occurred
                tuple[1] = analysis required

            No analysis required under the following scenarios:
                - entry same as previous entry
                - XR entry with epmRsMacEpToIpEpAtt update
                - local entry update without epmRsMacEpToIpEpAtt (for IP EPs)
        """
        if event is None: 
            logger.warn("ep_handle_event received no event")
            return (False, False)

        logger.debug("ep_handle_event event:%s" % (
            ept_utils.pretty_print(event)))

        # update vnid/epg name if present
        names = self.get_vnid_name(event["vnid"], event["pcTag"])
        if names is None: names ={"vnid_name":"","epg_name":""}

        # map remote entry for created/modified events with ifId present
        remote = ""
        if event["classname"]!="epmRsMacEpToIpEpAtt" and \
            event["status"]!="deleted" and len(event["ifId"])>0:
            # skip mapping of cached or unspecified interfaces
            if "cached" in event["flags"] or event["ifId"]=="unspecified":
                logger.debug("skipping remote map of cached/unspecified ep")
            elif not ept_utils.ep_is_local(event["flags"]):
                # on some versions of code (maybe all) ifId set to local/peer
                # vpc interface instead of tunnel. Therefore, always use
                # peer-node for peer-attached endpoints
                if "peer-attached" in event["flags"]:
                    remote = self.get_peer_node(event["node"])
                # for VTEPs interface may be unspecified, don't try to resolve
                elif "vtep" in event["flags"]: pass
                elif "tunnel" not in event["ifId"]:   
                    if len(event["flags"])>0:
                        logger.warn("remote entry w/o tunnel ifId: %s" % event)
                    else:
                        logger.debug("skipping remote mapping for %s" % event)
                else:
                    remote = self.get_remote_node(event["node"],event["ifId"])
                    if remote is None: remote = ""

        # map port-channel to vpc-id if mapping exists
        if "po" in event["ifId"]:
            vpc_id = self.get_vpc_from_pc(event["node"], event["ifId"])
            if vpc_id is not None: event["ifId"] = vpc_id

        # build database entry
        entry = {
            "ts": event["ts"],
            "dn": event["dn"],
            "status": event["status"],
            "vrf": event["vrf"] if "vrf" in event else "",
            "bd": event["bd"] if "bd" in event else "",
            "ifId": event["ifId"],
            "addr": event["addr"],
            "pcTag": event["pcTag"],
            "flags": event["flags"],
            "encap": event["encap"] if "encap" in event else "",
            "remote": remote,
            "rw_mac": "",
            "rw_bd": "",
            "vnid_name": names["vnid_name"],
            "epg_name": names["epg_name"],
            "_c": event["classname"]        # last class to update entry
        }

        if event["classname"] == "epmRsMacEpToIpEpAtt":
            compare_fields = epm_sub2_change_fields
            entry["addr"] = event["ip"]
            if event["status"] != "deleted":
                entry["rw_mac"] = event["addr"]
                entry["rw_bd"] = event["bd"]
        else:
            compare_fields = epm_sub1_change_fields
            if event["status"] == "deleted":
                # set entry to deleted entry w/o rewrite info
                entry={ "dn": "", "pcTag":"", "flags":"", "ifId":"", 
                        "encap":"", "rw_bd":"", "rw_mac":"", "remote":"", 
                        "vrf":"", "bd":"",
                        "status": "deleted", "vnid_name":"", "epg_name":"",
                        "addr": event["addr"], "ts": event["ts"],
                        "_c": event["classname"] # last class to update entry
                }

        # events are per-node, augment key to include node and fabric 
        # for db lookup
        db_key = {
            "fabric": self.fabric, "type": event["type"], "addr":entry["addr"],
            "vnid": event["vnid"], "node": event["node"]
        }

        update = False
        with self.app.app_context():
            db = self.app.mongo.db
            h = db.ep_history.find_one(db_key, {"events":{"$slice":1}})
            if h is None or "events" not in h or len(h["events"])==0:
                if entry["status"]=="deleted" or entry["status"]=="modified":
                    m ="ignoring deleted/modified event for non-existing entry"
                    logger.debug(m)
                    return (False, False)
                logger.debug("key is new on node-%s: %s"%(event["node"],db_key))
                # add new(1st) entry to database
                if not ept_utils.push_event(
                    db = db, rotate = self.max_ep_events, key=db_key,
                    table = "ep_history", event=entry):
                    logger.warn("failed to add update to db(%s: %s)" % (
                            db_key, entry))
                    return (False, False)
                # epmRsMacEpToIpEpAtt for none-existing entry should never
                # trigger an analysis.  Also, if event is local and this is
                # the first event, then rewrite is missing, so no analysis.
                # Therefore, the only event that can trigger analysis with 
                # no existing history is a epmMacEp or epmMacIp XR event
                if event["classname"] == "epmRsMacEpToIpEpAtt":
                    logger.debug("create for rewrite, no ip yet: no analyze")
                    return (True, False)
                elif event["classname"] == "epmIpEp" and \
                    ept_utils.ep_is_local(entry["flags"]):
                    logger.debug("update to local IP w/ no rewrite: no analyze")
                    return (True, False)
                else:
                    logger.debug("new event requires analyze")
                    return (True, True)

            # set h to last event in history
            h = h["events"][0]

            # compare timestamp first. If database entry is newer than event
            # then ignore event.  If last classname that update entry is diff
            # then current classname update entry, then ignore ts check
            if "ts" in h and h["ts"] > event["ts"] and ("_c" not in h or \
                event["classname"] == h["_c"]):
                logger.debug("event less recent than db entry (%f<%f)"% (
                    event["ts"], h["ts"]))
                return (False, False)

            # compare entry with previous entry. If deleted event, then add
            # deleted entry maintaining rewrite info for epmIpEp.  If modified
            # event then merge with previous result only changing values 
            # present in modify.  If created, then add full entry without any
            # merge. 
            if event["classname"] == "epmRsMacEpToIpEpAtt": 
                # need to merge subset of fields with previous entry for Rs
                for a in epm_rs_merge_fields:
                    if a in h: entry[a] = h[a]
                    
            elif event["classname"] == "epmIpEp":
                # need to merge subset of fields with previous entry for Ip
                entry["rw_mac"] = h["rw_mac"]
                entry["rw_bd"] = h["rw_bd"]
            
            if entry["status"] == "modified":
                if h["status"] == "deleted":
                    logger.debug("ignoring modified event for deleted entry")
                    return (False, False)
                for a in compare_fields:
                    if (a in entry) and len(entry[a])>0 and \
                        (a not in h or entry[a]!=h[a]):
                        if a not in h: h[a] = None
                        logger.debug("update node-%s:%s from %s to %s" %(
                            event["node"], a, h[a], entry[a]))
                        update = True
                    elif (a not in entry) or len(entry[a])==0:
                        # merge fields not set in modify with existing entry
                        entry[a] = h[a]
                # epg_name and vnid_name not in compare field and not merged
                # (only merged by default on epmRsMacEpToIpEpAtt)
                # need to use value from names if available or merge from 
                # previous entry
                if event["classname"] == "epmMacEp" or \
                    event["classname"] == "epmIpEp":
                    if "epg_name" in names and len(names["epg_name"])>0: 
                        entry["epg_name"] = names["epg_name"]
                    elif "epg_name" in h: 
                        entry["epg_name"] = h["epg_name"]
                    if "vnid_name" in names and len(names["vnid_name"])>0:
                        entry["vnid_name"] = names["vnid_name"]
                    elif "vnid_name" in h: 
                        entry["vnid_name"] = h["vnid_name"]

            elif entry["status"] == "deleted":
                if h["status"] != "deleted":
                    logger.debug("status changed from %s to deleted" % (
                        h["status"]))
                    update = True
                elif event["classname"] == "epmRsMacEpToIpEpAtt" and \
                    (len(h["rw_mac"])>0 or len(h["rw_bd"])>0):
                    logger.debug("delete rewrite info for deleted ep")
                    update = True
                else:
                    logger.debug("ignoring deleted event for deleted entry")
            else:
                for a in compare_fields:
                    if (a in entry) and (a not in h or entry[a]!=h[a]):
                        if a not in h: h[a] = None
                        logger.debug("update node-%s:%s from %s to %s" %(
                            event["node"], a, h[a], entry[a]))
                        update = True
                        break

            # merge status with history for epmRsMacEpTopIpEpAtt after analysis
            if event["classname"] == "epmRsMacEpToIpEpAtt": 
                if "status" in h: entry["status"] = h["status"]

            # add event to database if update was found
            if update:
                if not ept_utils.push_event(
                    db = db, rotate = self.max_ep_events, key=db_key,
                    table = "ep_history", event=entry):
                    logger.warn("failed to add update to db(%s: %s)" % (
                            db_key, entry))
                    return (False, False)

        # return (update, analysis_required) where analysis happens except on:
        # - no update occurred
        # - XR entry with epmRsMacEpToIpEpAtt update
        # - local entry update without epmRsMacEpToIpEpAtt (for IP EPs)
        if not update:
            logger.debug("no update detected for endpoint")
            return (False, False)
        if event["classname"]=="epmRsMacEpToIpEpAtt":
            if event["status"] == "deleted":
                logger.debug("delete to rewrite info on IP ep: no analyze")
                return (True, False)
            elif not ept_utils.ep_is_local(entry["flags"]):
                logger.debug("update to rewrite info for XR ep: no analyze")
                return (True, False)
            logger.debug("update to rewrite info for local ep: analyze")
            return (True, True)
        elif event["classname"] == "epmIpEp":
            if ept_utils.ep_is_local(entry["flags"]) and \
                len(entry["rw_mac"])==0:
                logger.debug("update to local IP ep w/ no rewrite: no analyze")
                return (True, False)
        logger.debug("update requires analyze")
        return (True, True)

    def ep_refresh(self, key, event_ts=None):
        """ perform manual refresh of endpoint state and feed through 
            ep_handle_event returning final update/analyze result
            
            return tuple of two booleans where:
                tuple[0] = update occurred
                tuple[1] = analysis required
        """
        # validate key has all required attributes
        if "type" not in key or "addr" not in key or "vnid" not in key:
            logger.error("key missing one or more required attributes: %s"%key)
            return (None,None)
        logger.debug("ep_refresh (type:%s, vnid:%s, addr:%s) event_ts:%s" % (
            key["type"], key["vnid"], key["addr"], event_ts))

        # get current list of nodes with non-deleted status and oldest ts
        h_node = {} 
        db_key = {"fabric":self.fabric,"vnid":key["vnid"],"type":key["type"],
            "addr":key["addr"]}
        oldest_history_ts = None
        with self.app.app_context():
            db = self.app.mongo.db
            for h in db.ep_history.find(db_key,{"events":{"$slice":1}}):
                if "events" in h and len(h["events"])>0:
                    if "ts" in  h["events"][0] and (oldest_history_ts is None \
                        or h["events"][0]["ts"]<oldest_history_ts):
                        oldest_history_ts = h["events"][0]["ts"]
                    # track non-deleted nodes
                    if "status" in h["events"][0] and \
                        h["events"][0]["status"]!="deleted":
                            h_node[h["node"]] = {"refresh":0,"history":h}

        # don't process job events that are older than all history events
        if event_ts is not None and oldest_history_ts is not None and \
            event_ts < oldest_history_ts:
            logger.debug("stop ep_refresh request as %f < %f" % (
                event_ts, oldest_history_ts))
            return (None,None)

        # perform refresh for endpoint
        kwargs={}
        if key["type"]=="ip":
            # pull both epmIpEp and epmRsMacEpToIpEpAtt for ip EP refreshes
            qclass = "epmDb"
            kwargs["queryTarget"] = "subtree"
            kwargs["targetSubtreeClass"] = "epmIpEp,epmRsMacEpToIpEpAtt"
            qtf = "or(eq(epmIpEp.addr,\"%s\")," % key["addr"]
            qtf+= "wcard(epmRsMacEpToIpEpAtt.dn,\"ip-\\[%s\\]\"))"%(key["addr"])
            kwargs["queryTargetFilter"] = qtf
        else:
            qclass = "epmMacEp"
            kwargs["queryTargetFilter"]="eq(epmMacEp.addr,\"%s\")"%(key["addr"])
        if self.session is None: 
            self.session = ept_utils.get_apic_session(self.fabric)
            if self.session is None:
                logger.warn("failed to get valid apic session")
                return (None,None)
        # two tries to pull data
        logger.debug("get_class: (%s,%s)" % (qclass, kwargs))
        js = ept_utils.get_class(self.session, qclass, **kwargs)
        if js is None:
            logger.warn("get_class: (%s,%s) failed, retry"% (qclass,kwargs))
            self.session = ept_utils.refresh_session(self.fabric,None)
            if self.session is None: 
                logger.warn("failed to get valid apic session")
                return (None,None)
            js = ept_utils.get_class(self.session, qclass, **kwargs)
            if js is None:
                logger.warn("failed refresh key: %s" % key)
                return (None,None)

        # create ep_analyze event for each object received
        events = []
        for obj in js:
            classname = obj.keys()[0]
            key = ept_utils.parse_epm_event(classname,obj,self.overlay_vnid,
                ts=event_ts)
            if key is not None:
                events.append(key)
                if key["node"] in h_node: h_node[key["node"]]["refresh"] = 1

        # create delete event for all history nodes not found in refresh
        for node in h_node:
            if h_node[node]["refresh"] == 0:
                h = h_node[node]["history"]
                delete_jobs = ep_get_delete_jobs(h, self.overlay_vnid, 
                    event_ts=event_ts)
                if delete_jobs is None:
                    logger.warn("failed to get delete_jobs for %s" % h)
                else:
                    for j in delete_jobs: events.append(j.data)

        # run each job through ep_handle_event and OR together result
        update = False
        analyze = False
        for e in events:
            (u,a) = self.ep_handle_event(e)
            if u is None or a is None: 
                update = None
                analyze = None
            elif update is not None:
                update|= u
                analyze|= a
        return (update, analyze)
        
    def get_last_events(self, events, ep_type):
        """ look back through provided events from ep_history for single node
            and return the last two complete events accounting for transitory
            deletes/rewrite updates
            transitory delete requires a timeout (transitory_delete_time)
            ep_type must be 'mac' or 'ip'.  'ip' requires tracking of rewrite
            Returns list of last complete events (none on error)
        """
        last_event = []
        for e in events:
            # add delete event if not a transitory event
            if e["status"] == "deleted": 
                if len(last_event)==0 or self.transitory_delete_time<=0 or \
                    (last_event[0]["ts"]-e["ts"])>self.transitory_delete_time:
                    last_event.append(e)
                else: continue

            # skip events without an interface or cached endpoints w/ 
            # 'unspecified' interfaces - note XR entries will if tunnel ifId
            # so should never be empty. local entries will have correct ifId
            elif "cached" in e["flags"] or len(e["ifId"])==0 or \
                e["ifId"]=="unspecified": 
                continue
           
            # add local events if rewrite info is present or type mac 
            elif ept_utils.ep_is_local(e["flags"]):
                if ep_type == "ip":
                    if len(e["rw_mac"])>0 and len(e["rw_bd"])>0:
                        last_event.append(e)
                    else: continue
                else: 
                    last_event.append(e)
 
            # skip ip XR event if last event was same XR with only difference
            # of rewrite info - since rewrite info updates are also
            # transitory events
            else:   
                if len(last_event)==1 and ep_type == "ip" \
                    and not ept_utils.ep_is_local(last_event[0]["flags"]) \
                    and last_event[0]["remote"] == e["remote"] \
                    and last_event[0]["rw_mac"] != e["rw_mac"]:
                        continue
                else:
                    last_event.append(e)

            # stop after 2 events are found
            if len(last_event)>=2: break
                   
        return last_event
                
    def ep_analyze_move(self, key):
        """ find the last local events within database for endpoint and
            analyze for move.  If move has occurred, then add to database
            if not already present.
            return move update dict {src: info, dst: info} on successful
            insertion into database
            return None on error
        """
        # validate key has all required attributes
        if "type" not in key or "addr" not in key or "vnid" not in key:
            logger.error("key missing one or more required attributes: %s"%key)
            return None

        logger.debug("analyze move (vnid:%s,addr:%s)"%(key["vnid"],key["addr"]))
        db_key = {
            "fabric": self.fabric,
            "type": key["type"], "addr": key["addr"], "vnid": key["vnid"],
        }
        self.last_db_read_key = db_key
        last_local = [None, None]
        with self.app.app_context():
            db = self.app.mongo.db
            h_count = 0
            self.last_db_read_value = []
            for h in db.ep_history.find(db_key,{"events":{"$slice":5}}):
                self.last_db_read_value.append(h)
                h_count+= 1
                l = self.get_last_events(h["events"], h["type"])
                # at most two events returned from last_events. find the two
                # most recent local events and set them to last_local
                if l is None or len(l)==0: continue
                if ept_utils.ep_is_local(l[0]["flags"]):
                    if last_local[0] is None or l[0]["ts"]>last_local[0]["ts"]:
                        last_local[0] = l[0]
                        # l is just the events - need to add the 'node' attr
                        last_local[0]["node"] = h["node"]
                if len(l)==2 and ept_utils.ep_is_local(l[1]["flags"]):
                    if last_local[1] is None or l[1]["ts"]>last_local[1]["ts"]:
                        last_local[1] = l[1]
                        # l is just the events - need to add the 'node' attr
                        last_local[1]["node"] = h["node"]

        if h_count == 0:
            logger.warn("endpoint %s not found on any node" % db_key)
            return {}
        if last_local[0] is None:
            logger.debug("state is XR or deleted on all nodes, not a move")
            return {}
        if last_local[1] is None:
            logger.debug("last state is XR or deleted on all nodes, not a move")
            return {}

        # update node number to vpc representation if ep is on vpc
        if "vpc-attached" in last_local[0]["flags"]:
            pn = self.get_peer_node(last_local[0]["node"])
            if pn is None:
                logger.warn("failed to find peer of %s for vpc-attached ep"%(
                    last_local[0]["node"]))
                return None
            last_local[0]["node"] = "%s" % get_vpc_domain_id(
                                            last_local[0]["node"], pn)
        if "vpc-attached" in last_local[1]["flags"]:
            pn = self.get_peer_node(last_local[1]["node"])
            if pn is None:
                logger.warn("failed to find peer of %s for vpc-attached ep"%(
                    last_local[1]["node"]))
                return None
            last_local[1]["node"] = "%s" % get_vpc_domain_id(
                                            last_local[1]["node"], pn)

        # do move analysis between last_local events
        logger.debug("last local events from %s to %s" % (last_local[1], 
            last_local[0]))
        move = {}
        for attr in epm_move_fields:
            if last_local[0][attr] != last_local[1][attr]:
                logger.debug("move detected %s from %s to %s" % (
                    attr, last_local[1][attr], last_local[0][attr]))
                move["src"] = {}
                move["dst"] = {}
                for m in epm_move_fields+["ts", "epg_name", "vnid_name"]:
                    move["src"][m] = ""
                    move["dst"][m] = ""
                    if m in last_local[1]: move["src"][m] = last_local[1][m]
                    if m in last_local[0]: move["dst"][m] = last_local[0][m]
                break
        if len(move) == 0:
            logger.debug("no move detected")
            return move

        # check if entry is already in database, if not add it
        updates = {}
        with self.app.app_context():
            db = self.app.mongo.db
            entry = db.ep_moves.find_one(db_key)
            if entry is None or "events" not in entry or \
                len(entry["events"])==0:
                updates = move
            else:
                last_move = entry["events"][0]
                # check if event is older than last event 
                # (corner case with rapid moves involving vpc pairs)
                if last_move["dst"]["ts"] > move["dst"]["ts"]:
                    logger.debug("move is less recent than previous move")
                    return {}
                # if everything is same in last_move[dst] then assume this is
                # a duplicate move event
                for attr in epm_move_fields:
                    if attr not in last_move["dst"] or \
                        last_move["dst"][attr]!=move["dst"][attr]:
                        updates = move
                        break 
            if len(updates) == 0:
                logger.debug("move is duplicate of previous event")
                return updates

            # push move event to database
            if not ept_utils.push_event(
                db = db, key = db_key, rotate = self.max_ep_events,
                table="ep_moves", event = updates, increment="count"):
                logger.warn("failed to add update to db(%s: %s)" % (
                    db_key, updates))
            return updates 

    def ep_analyze_stale(self, key):
        """ analyze endpoint from ep_history current state to determine if
            it is stale/incorrect.  If stale/incorrect, add to ep_stale table
            if not duplicate of the last entry.  
            Set is_stale on per-node endpoint in ep_history table.
            Return dict of updates added indexed by node id with stale index
            Returns None on error.
                key is dict requiring: type, addr, vnid
        """

        # TODO need to consider/test multipod bounce-to-proxy scenarios
        # For now, just focusing on correct entry

        # validate key has all required attributes
        if "type" not in key or "addr" not in key or "vnid" not in key:
            logger.error("key missing one or more required attributes: %s"%key)
            return None

        # get current state of endpoint from database and determine local node 
        db_key = {
            "fabric": self.fabric, "vnid":key["vnid"], "type": key["type"],
            "addr": key["addr"]
        }
        logger.debug("ep analyze stale for key: %s" % db_key)
        nodes = {}
        local_node = None
        with self.app.app_context():
            db = self.app.mongo.db

            # clear is_stale flag on all nodes before analysis (will be set
            # on any nodes that are determined to be stale)
            db.ep_history.update_many(db_key, {"$set":{"is_stale":False}})

            # check if we need to read from database or if data is saved 
            # from prior ep_analyze_move
            if self.last_db_read_key is not None and \
                self.last_db_read_value is not None and \
                self.last_db_read_key == db_key:
                all_h = self.last_db_read_value
            else:
                all_h = db.ep_history.find(db_key, {"events":{"$slice":1}})
            for h in all_h:
                if "node" not in h or "events" not in h:
                    logger.warn("skipping invalid ep_history object: %s" % h)
                    continue
                if len(h["events"])>0 and "flags" in h["events"][0]:
                    if h["node"] in nodes:
                        logger.warn("skipping duplicate node(%s) for key(%s)"%(
                            h["node"], db_key))
                        continue
                    # state might be 'deleted', ignore these nodes
                    if "status" in h["events"][0] and \
                        h["events"][0]["status"] == "deleted":
                        continue
                    nodes[h["node"]] = h["events"][0]
                    if ept_utils.ep_is_local(h["events"][0]["flags"]):
                        n = h["node"]
                        if "vpc-attached" in h["events"][0]["flags"]:
                            pn = self.get_peer_node(h["node"])
                            if pn is None or pn is "":
                                logger.warn("failed to find vpc peer for %s"%n)
                                return None
                            n = "%s" % get_vpc_domain_id(n, pn)
                        if local_node is not None and local_node != n:
                            em = "unable to determine correct local node:"
                            em+= " (%s)!=(%s)" % (local_node, n)
                            logger.debug("%s, state: %s" % (em, nodes))
                            return {}   # don't force an error, just stop
                        local_node = n
    
        # dict of nodes determined to be stale for this endpoint
        stale_nodes = {}
        if len(nodes)==0:
            logger.debug("endpoint deleted from all nodes - no stale entries")
            return {}
        elif local_node is None:
            logger.debug("no local node found") 
            # force local_node to "0" implying it was deleted
            local_node = "0"
            for node in nodes:
                state = nodes[node]
                state["expected_remote"] = local_node
                logger.debug("(no local) stale on %s to %s" % (
                    node, get_node_string(state["remote"])))
                stale_nodes[node] = state
        else:
            logger.debug("local on %s" % get_node_string(local_node))

            # for each node check if it is pointing to correct entry or allow
            # for single bounce
            for node in nodes:
                state = nodes[node]
                # already checked nodes with local entries are correct
                if ept_utils.ep_is_local(state["flags"]): continue
                # check that remote entry is pointing to correct node
                if state["remote"] == local_node: continue
                # if flag is bounce-to-proxy, then endpoint is ok on this node
                if "bounce-to-proxy" in state["flags"]: continue

                # map remote node id to 1 or 2 nodes (incase 'remote' is vpc id)
                # and check ALL have correct pointer
                for rn in get_nodes_from_vpc_id(state["remote"]):
                    if rn not in nodes:
                        # rn pointing to node that doesn't have the ep present
                        stale_nodes[node] = state
                        logger.debug("stale on %s pointing to wrong node %s"%(
                            node, get_node_string(rn)))
                    elif not ept_utils.ep_is_local(nodes[rn]["flags"]) and \
                        (nodes[rn]["remote"] != local_node or \
                        "bounce" not in nodes[rn]["flags"]):
                        stale_nodes[node] = state
                        logger.debug("stale on %s to %s (%s -> %s)" % (
                            node, get_node_string(rn),nodes[rn]["flags"],
                            nodes[rn]["remote"]))
                    else:
                        logger.debug("remote on %s to %s (%s -> %s)" % (
                            node, get_node_string(rn),nodes[rn]["flags"],
                            nodes[rn]["remote"]))

        # no stale nodes found
        if len(stale_nodes) == 0: 
            logger.debug("no stale entries for endpoint")
            return {}
                
        # check if entry is already in database, if not add it
        updates = {}
        with self.app.app_context():
            db = self.app.mongo.db

            # for all nodes currently found as stale, update is_stale flag
            per_node_key = {"fabric": self.fabric, "vnid":key["vnid"], 
                "type": key["type"], "addr": key["addr"], "node":""}
            for node in stale_nodes:
                per_node_key["node"] = node
                logger.debug("setting is_stale to True for node %s" % node)
                db.ep_history.update_one(per_node_key, {
                    "$set":{"is_stale":True}})

            for entry in db.ep_stale.find(db_key):
                if entry["node"] not in stale_nodes: continue
                # set 'ce' to current stale event were are doing dup check
                ce = stale_nodes.pop(entry["node"])
                ce["expected_remote"] = local_node
                if "events" not in entry or len(entry["events"])==0:
                    updates[entry["node"]] = ce
                    continue
                # compare state of last entry to see if it is same as 
                # current entry by just checking remote value and ts
                le = entry["events"][0]
                if "remote" not in ce or "remote" not in le or \
                    ce["remote"] != le["remote"] or \
                    "ts" not in ce or "ts" not in le or \
                    ce["ts"] != le["ts"]:
                    updates[entry["node"]] = ce
                else:
                    logger.debug("stale on %s is duplicate of last event"%(
                        entry["node"]))
                    #logger.debug("last: %s, current: %s" % (
                    #    ept_utils.pretty_print(le),ept_utils.pretty_print(ce)))

            # any entries still in stale_nodes were not previously in database
            for node in stale_nodes:
                stale_nodes[node]["expected_remote"] = local_node
                updates[node] = stale_nodes[node]

            # stale double check functionality uses different worker to ensure
            # current stale event is not a transistory event - only push to 
            # database in this funciton if stale double check is disabled
            if not self.stale_double_check:
                # push event updates to database
                for node in updates:
                    db_key["node"] = node
                    if not ept_utils.push_event(
                        db = db,key=db_key,rotate = self.max_ep_events,
                        table="ep_stale", event=updates[node],
                        increment="count"):
                        logger.warn("failed to add update to db(%s: %s)" % (
                            db_key, updates[node]))

        if len(updates) == 0:
            logger.debug("no new stale entries for endpoint(vnid:%s,addr:%s)"%(
                key["vnid"], key["addr"]))

        # return dict of updates indexed by node-id that occurred as result
        # of refresh
        return updates

    def ep_analyze_offsubnet(self, key):
        """ analyze endpoint from ep_history current state to determine if
            it has been learned offsubnet.  If so, add to ep_offsubnet table
            if not duplicate of the last entry.  
            Set is_offsubet on per-node endpoint in ep_history table.
            Return dict of updates added indexed by node id that is offsubnet
            Returns None on error.
                key is dict requiring: type, addr, vnid
        """

        # validate key has all required attributes
        if "type" not in key or "addr" not in key or "vnid" not in key:
            logger.error("key missing one or more required attributes: %s"%key)
            return None

        # get current state of endpoint from database and determine local node 
        db_key = {
            "fabric": self.fabric, "vnid":key["vnid"], "type": key["type"],
            "addr": key["addr"]
        }
        if key["type"] != "ip": 
            logger.debug("skipping offsubnet analysis for type %s"%key["type"])
            return {}
        logger.debug("ep analyze offsubnet for key: %s" % db_key)

        offsubnet_nodes = {}
        updates = {}
        with self.app.app_context():
            db = self.app.mongo.db
            # clear is_offsubnet flag on all nodes before analysis (will be set
            # on any nodes that are determined to be offsubnet)
            db.ep_history.update_many(db_key, {"$set":{"is_offsubnet":False}})
            # check if we need to read from database or if data is saved 
            # from prior ep_analyze_move
            if self.last_db_read_key is not None and \
                self.last_db_read_value is not None and \
                self.last_db_read_key == db_key:
                all_h = self.last_db_read_value
            else:
                all_h = db.ep_history.find(db_key, {"events":{"$slice":1}})
            for h in all_h:
                # ensure status is present
                if "node" not in h or "events" not in h or \
                    len(h["events"])==0 or "status" not in h["events"][0] \
                    or "pcTag" not in h["events"][0]:
                    logger.warn("skipping invalid ep_history object: %s" % h)
                    continue
                # state might be 'deleted', ignore these nodes
                if "status" in h["events"][0] and \
                    h["events"][0]["status"] == "deleted":
                    continue
                # skip check for pcTag 'any' or if pcTag is not set
                if h["events"][0]["pcTag"] == "any" or \
                    len(h["events"][0]["pcTag"])==0: continue
                # check if endpoint is offsubnet
                is_offsubnet = self.ep_is_offsubnet(key["vnid"],key["addr"],
                    h["events"][0]["pcTag"])
                if is_offsubnet is None:
                    logger.debug("node-%s: %s on %s,%s is_offset check: %s"%(
                        h["node"], key["addr"], key["vnid"],
                        h["events"][0]["pcTag"], is_offsubnet))
                    continue
                logger.debug("node-%s: %s on %s,%s is_offsubnet: %r" % (
                    h["node"], key["addr"], key["vnid"], 
                    h["events"][0]["pcTag"], is_offsubnet))
                if is_offsubnet:
                    offsubnet_nodes[h["node"]] = h["events"][0]

            # no stale nodes found
            if len(offsubnet_nodes) == 0: 
                logger.debug("no offsubnet entries for endpoint")
                return {}

            # for all nodes currently found as offsubnet, update flag
            per_node_key = {"fabric": self.fabric, "vnid":key["vnid"], 
                "type": key["type"], "addr": key["addr"], "node":""}
            for node in offsubnet_nodes:
                per_node_key["node"] = node
                logger.debug("setting is_offsubnet to True for node %s" % node)
                db.ep_history.update_one(per_node_key, {
                    "$set":{"is_offsubnet":True}})

            # check if entry is already in database, if not add it
            for entry in db.ep_offsubnet.find(db_key):
                if entry["node"] not in offsubnet_nodes: continue
                # set 'ce' to current offsubnet event were are doing dup check
                ce = offsubnet_nodes.pop(entry["node"])
                if "events" not in entry or len(entry["events"])==0:
                    updates[entry["node"]] = ce
                    continue
                # compare state of last entry to see if it is same as 
                # current entry by just checking pcTag and ts
                le = entry["events"][0]
                if "pcTag" not in ce or "pcTag" not in le or \
                    ce["pcTag"] != le["pcTag"] or \
                    "ts" not in ce or "ts" not in le or \
                    ce["ts"] != le["ts"]:
                    updates[entry["node"]] = ce
                else:
                    logger.debug("offsubnet on %s is duplicate of last event"%(
                        entry["node"]))
                    logger.debug("last: %s, current: %s" % (
                        ept_utils.pretty_print(le),ept_utils.pretty_print(ce)))

            # any entries still in stale_nodes were not previously in database
            for node in offsubnet_nodes: updates[node] = offsubnet_nodes[node]

            # double check functionality uses different worker to ensure
            # current offsubnet event is not a transistory event - only push to 
            # database in this funciton if double check is disabled
            if not self.offsubnet_double_check:
                # push event updates to database
                for node in updates:
                    db_key["node"] = node
                    if not ept_utils.push_event(
                        db = db,key=db_key,rotate = self.max_ep_events,
                        table="ep_offsubnet", event=updates[node],
                        increment="count"):
                        logger.warn("failed to add update to db(%s: %s)" % (
                            db_key, updates[node]))

        if len(updates) == 0:
            logger.debug("no new offsubnet events for ep(vnid:%s,addr:%s)"%(
                key["vnid"], key["addr"]))

        # return dict of updates indexed by node-id
        return updates


    def ep_notify_move(self, key, move):
        """ if enabled, send notification for endpoint move
                key is dict requiring: type, addr, vnid
                move is dict containing 'src' and 'dst' keys
        """
        # validate if notifications are enabled/configured for ep moves
        if (not self.notify_move_email or len(self.notify_email)==0) and \
            (not self.notify_move_syslog or len(self.notify_syslog)==0):
            logger.debug("notify move not enabled")
            return

        # validate key has all required attributes
        if "type" not in key or "addr" not in key or "vnid" not in key:
            logger.error("key missing one or more required attributes: %s"%key)
            return
        if "src" not in move or "dst" not in move:
            logger.error("move missing one or more attributes:%s"%move)
            return
        for attr in ["node", "ifId", "encap", "pcTag", "rw_bd", "rw_mac",
            "epg_name", "vrf_name"]:
            if attr not in move["src"] or len(move["src"][attr])==0:
                move["src"][attr] = "-"
            if attr not in move["dst"] or len(move["dst"][attr])==0:
                move["dst"][attr] = "-"

        if key["type"] == "ip":
            src_str="[node:%s,ifId:%s,encap:%s,pcTag:%s,mac:%s,epg:%s]"%(
                get_node_string(move["src"]["node"]),
                move["src"]["ifId"], move["src"]["encap"],
                move["src"]["pcTag"], move["src"]["rw_mac"], 
                move["src"]["epg_name"])
            dst_str="[node:%s,ifId:%s,encap:%s,pcTag:%s,mac:%s,epg:%s]"%(
                get_node_string(move["dst"]["node"]),
                move["dst"]["ifId"], move["dst"]["encap"],
                move["dst"]["pcTag"], move["dst"]["rw_mac"], 
                move["dst"]["epg_name"])
        else:
            # no rewrite info for mac endpoint
            src_str="[node:%s,ifId:%s,encap:%s,pcTag:%s,epg:%s]"%(
                get_node_string(move["src"]["node"]),
                move["src"]["ifId"], move["src"]["encap"],
                move["src"]["pcTag"], move["src"]["epg_name"])
            dst_str="[node:%s,ifId:%s,encap:%s,pcTag:%s,epg:%s]"%(
                get_node_string(move["dst"]["node"]),
                move["dst"]["ifId"], move["dst"]["encap"],
                move["dst"]["pcTag"], move["dst"]["epg_name"])

        # vnid should not change between src/dst, grab value from source
        vnid_name = ""
        if key["type"] == "ip":
            if len(move["src"]["vnid_name"])>0:
                vnid_name=",vrf:%s" % move["src"]["vnid_name"]
        else:
            if len(move["src"]["vnid_name"])>0:
                vnid_name=",bd:%s" % move["src"]["vnid_name"]
        msg = "move detected [fabric:%s%s,addr:%s,vnid:%s] from %s to %s" % (
            self.fabric, vnid_name, key["addr"], key["vnid"], src_str, dst_str)

        logger.debug("notify move: %s" % msg)
        # send email if enabled
        if self.notify_move_email and len(self.notify_email)>0:
            logger.debug("sending email to %s" % self.notify_email)
            ept_utils.email(to=self.notify_email, msg=msg,
                subject = "move detected [fabric:%s%s,addr:%s,vnid:%s]" % (
                    self.fabric, vnid_name, key["addr"], key["vnid"])
            )
        # send syslog if enabled
        if self.notify_move_syslog and len(self.notify_syslog)>0:
            logger.debug("sending syslog to %s" % self.notify_syslog)
            ept_utils.syslog(
                severity = "info", server=self.notify_syslog,
                port = self.notify_syslog_port, msg = msg)

    def ep_notify_stale(self, key, event):
        """ alias for ep_notify_event with notify_type='stale' """
        return self.ep_notify_event(key, event, notify_type="stale")

    def ep_notify_offsubnet(self, key, event):
        """ alias for ep_notify_event with notify_type='offsubnet' """
        return self.ep_notify_event(key, event, notify_type="offsubnet")

    def ep_notify_event(self, key, event, notify_type="stale"):
        """ if enabled, send notification for per-node events
                key is dict requiring: type, addr, vnid, node
                    * stale requires 'remote' and 'expected_remote' attr
                event should contain 'vnid_name' and 'epg_name' 
        """
        # validate if notifications are enabled/configured
        d_msg = ""
        send_email = False
        send_syslog = False
        if notify_type == "stale":
            send_email = self.notify_stale_email and \
                            len(self.notify_email)>0
            send_syslog = self.notify_stale_syslog and \
                            len(self.notify_syslog)>0
            # further verificatons specific to stale events
            if "remote" not in event or "expected_remote" not in event:
                logger.error("stale missing one or more attributes: %s"%event)
                return
            d_msg = " [current-node:%s,expected-node:%s]" % (
                get_node_string(event["remote"]), 
                get_node_string(event["expected_remote"]))
        elif notify_type == "offsubnet":
            send_email = self.notify_offsubnet_email and \
                            len(self.notify_email)>0
            send_syslog = self.notify_offsubnet_syslog and \
                            len(self.notify_syslog)>0
            if "epg_name" in event and len(event["epg_name"])>0: 
                d_msg = " epg: %s" % event["epg_name"]
        elif "clear" in notify_type.lower():
            # expect clear events to be either 'cleared' or 'failed to clear'
            send_email = len(self.notify_email)>0
            send_syslog = len(self.notify_syslog)>0

        if not send_email and not send_syslog:
            logger.debug("notify event not enabled")
            return

        # validate key has all required attributes
        if "type" not in key or "addr" not in key or "vnid" not in key or \
            "node" not in key:
            logger.error("key missing one or more required attributes: %s"%key)
            return

        vnid_name = ""
        if "vnid_name" in event and key["type"] == "ip":
             vnid_name=",vrf:%s" % event["vnid_name"]
        elif "vnid_name" in event and key["type"] == "mac":
            vnid_name=",bd:%s" % event["vnid_name"]
        msg = "%s endpoint [fabric:%s%s,addr:%s,vnid:%s] " % (
            notify_type, self.fabric, vnid_name, key["addr"], key["vnid"])
        msg+= "on node %s" % (get_node_string(key["node"]))

        logger.debug("notify event: %s" % msg)
        # send email if enabled
        if send_email:
            logger.debug("sending email to %s" % self.notify_email)
            ept_utils.email(to=self.notify_email, subject=msg, 
                msg = "%s%s" % (msg, d_msg))
        # send syslog if enabled
        if send_syslog:
            logger.debug("sending syslog to %s" % self.notify_syslog)
            ept_utils.syslog(
                severity = "info", server=self.notify_syslog,
                port = self.notify_syslog_port, msg ="%s%s" % (msg, d_msg))


    def ep_notify_fail(self, job):
        """ remove all jobs from current rxQ that match key of notify job.
            Then, if notifications are enabled (only syslog for now), 
            notify that application is unable to process provided key 
            indicating that the endpoint is likely moving rapidly in the fabric
        """

        logger.debug("removing all jobs from RxQ with key: %s" % job.key)
        requeue = []
        remove_count = 0
        last_remove_count = 0
        fail_count = 0
        while True:
            try: 
                tjob = self.rxQ.get_nowait()
                if tjob.key == job.key: remove_count+=1
                else: requeue.append(tjob)
            except Empty: 
                if self.rxQ.qsize() > 0: 
                    logger.debug("no_wait triggered empty with rxQ:%s"%(
                        self.rxQ.qsize()))
                    if remove_count>0 and last_remove_count == remove_count:
                        fail_count+= 1
                        if fail_count >= 3:
                            logger.warn("stop waiting for get_nowait")
                            break
                    last_remove_count = remove_count
                    time.sleep(0.005)
                else: break
        logger.debug("removed %s jobs with key %s from rxQ" % (
            remove_count, job.key))
        logger.debug("re-adding %s jobs back onto rxQ" % len(requeue))
        for t in requeue: self.rxQ.put(t)

        # only support syslog for 
        if len(self.notify_syslog)==0:
            logger.debug("notify fail is not enabled")
            return

        # validate key has all required attributes
        key = job.key
        if "type" not in key or "addr" not in key or "vnid" not in key:
            logger.error("key missing one or more required attributes: %s"%key)
            return

        vnid_name = ""
        names = self.get_vnid_name(key["vnid"])
        if names is not None and "vnid_name" in names:
            if key["type"] == "ip": vnid_name=",vrf:%s" % (names["vnid_name"])
            elif key["type"] == "mac": vnid_name=",bd:%s" % (names["vnid_name"])
    
        msg = "failed to process endpoint [fabric:%s%s,addr:%s,vnid:%s] " % (
            self.fabric, vnid_name, key["addr"], key["vnid"])
        logger.debug("notify failed ep: %s" % msg)

        # send syslog if enabled
        logger.debug("sending syslog to %s" % self.notify_syslog)
        ept_utils.syslog(
            severity = "info", server=self.notify_syslog,
            port = self.notify_syslog_port, msg = msg)

    def watch_event(self, job):
        """ recevies two types of jobs:
                1) execute_ts is set to None. This is job from parent with
                    job.data containing lists of nodes that are stale/offsubnet
                     for provided job.key.  They key+node may represent a key in
                    self.watched that is already watched.  If so, update the
                    execute_ts in the job. 
                2) execute_ts is not NONE. This is job from callback where
                    wait time has expired and its time to add endpoint to
                    ep_stale/ep_offsubnet and notify, else stop tracking
                    endpoint if it is no longer in affected state. This job 
                    is per-node
            supported events (per-node):
                watch_stale     - endpoint is_stale flag set
                watch_offsubnet - endpoint is_offsubnet flag set
        """     
        watch_name = job.action
        if job.execute_ts is None:
            logger.debug("[%s] %s for new ep: %s,data:%s" %(self,watch_name,
                job.key, ept_utils.pretty_print(job.data)))
            ts = time.time()
            for node in job.data:
                # if stale XR entry has expected_remote of "0", then use
                # transitory_xr_stale_time
                if "expected_remote" in job.data[node] and \
                    job.data[node]["expected_remote"] == "0":
                    execute_ts = ts + self.transitory_xr_stale_time
                elif watch_name == "watch_stale":
                    execute_ts = ts + self.transitory_stale_time
                else:
                    execute_ts = ts + self.transitory_offsubnet_time
                nkey = {
                    "fabric":self.fabric, "type": job.key["type"], 
                    "addr":job.key["addr"], "vnid": job.key["vnid"], 
                    "node": node
                }
                n = EPJob(watch_name,nkey,ts=job.ts,execute_ts=execute_ts,
                    data=job.data[node])
                # if the modified ts on the event is same as current entry, 
                # then we need to ignore the event instead of extending time
                if n.keystr in self.watched:
                    old_j = self.watched[n.keystr]
                    if "ts" in old_j.data and "ts" in n.data and \
                        old_j.data["ts"]==n.data["ts"]:
                        logger.debug("ignoring %s for existing entry" % (
                            watch_name))
                        continue
                # overwrite or create new watch_event entry
                self.watched[n.keystr] = n
                logger.debug("added %s with execute_ts:%f (%s sec)" % (n, 
                    n.execute_ts, (n.execute_ts - ts)))
        else:
            # execute_ts is set so this is a callback function for single node
            # since is_stale/is_offsubnet is set in ep_history for this node, 
            # need only re-verify that flag is still set
            db_key = job.key
            event = job.data
            clear_endpoint = False
            if watch_name == "watch_stale": 
                is_flag = "is_stale"
                db_table = "ep_stale"
                notify = self.ep_notify_stale
                clear_endpoint = self.auto_clear_stale
            else: 
                is_flag = "is_offsubnet"
                db_table = "ep_offsubnet"
                notify = self.ep_notify_offsubnet
                clear_endpoint = self.auto_clear_offsubnet
            
            logger.debug("%s for key: %s" % (watch_name, db_key))
            with self.app.app_context():
                db = self.app.mongo.db
                h = db.ep_history.find_one(db_key,{"events":{"$slice":1}})
                if h is None or is_flag not in h or "events" not in h or \
                    len(h["events"])==0:
                    logger.warn("ep not found or %s missing: %s" % (h,is_flag))
                    return
                if not h[is_flag]:
                    logger.debug("ep no longer %s" % is_flag)
                    return

                # add event to database
                logger.debug("ep %s, adding to %s table" % (is_flag, db_table))
                if not ept_utils.push_event(
                    db = db,key=db_key,rotate = self.max_ep_events,
                    table=db_table, event=event, increment="count"):
                    logger.warn("failed to add update to db(%s: %s)" % (
                            db_key, event))

                # perform ep notify event, clear ep, and notify clear status
                notify(db_key, event)
                if clear_endpoint and "node" in db_key:
                    logger.debug("attempt to auto_clear endpoint")
                    self.ep_notify_event(db_key, h["events"][0], "clearing")
                    node = db_key["node"]
                    cmd = "--clear_endpoint --fabric %s --addr %s --vnid %s "%(
                        self.fabric, db_key["addr"], db_key["vnid"])
                    cmd+= "--nodes %s" % node
                    if ept_utils.worker_bypass(cmd):
                        logger.debug("worker_bypass cmd successful")
                    else:
                        logger.debug("worker_bypass cmd failed")
                else:
                    logger.debug("no auto_clear action required")

    def watch_node(self, job):
        """ receives job with data field containing following two keys:
                node: string node_id 
                status: 'active' or 'inactive' status
            - On inactive event, this function triggers a flush of all
            non-deleted endpoints currently learned on the inactive node
            - On active event, this function triggers a full epm refresh
            of all endpoints on the node.

            For both events, this function returns a single job whose
            data field contains a list of endpoint add/delete jobs with 
            appropriate keys and parsed epm events.
        """
        logger.debug("received watch_node job for: %s" % job.data)
        if "node" not in job.data or "status" not in job.data or \
            "pod" not in job.data:
            logger.warn("invalid or incomplete attributes received")
            return

        # this job may take a while to complete, extend hello time request
        # static to 90 seconds for now...
        self.extend_hello(90.0)

        dn = "topology/pod-%s/node-%s/sys" % (job.data["pod"], job.data["node"])
        jobs = []

        # pull all endpoints from apic for new active node via get request
        if job.data["status"] == "active":
            logger.debug("%s active, pulling all current endpoints" % dn)
            tsc = "epmMacEp,epmIpEp,epmRsMacEpToIpEpAtt"
            self.session = ept_utils.refresh_session(self.fabric)
            if self.session is None:
                logger.warn("failed to refresh apic session")
                return
            opts = ept_utils.build_query_filters(queryTarget="subtree",
                targetSubtreeClass=tsc)
            url = "/api/mo/%s.json%s" % (dn,opts)
            js = ept_utils.get(self.session, url)
            if js is None:
                logger.warn("get_dn: %s returned None" % url)
                return
            logger.debug("received %s objects from node refresh" % len(js))
            for obj in js:
                classname = obj.keys()[0]
                key = ept_utils.parse_epm_event(classname,obj,self.overlay_vnid)
                if key is not None:
                    jkey = {
                        "type": key["type"],
                        "addr": key["addr"],
                        "vnid": key["vnid"]
                    }
                    # for epmRsMacEpToIpEpAtt, remap addr from mac to ip attr
                    if classname=="epmRsMacEpToIpEpAtt": jkey["addr"]=key["ip"]
                    jobs.append(EPJob("ep_analyze",jkey,ts=key["ts"],data=key))
                else:
                    logger.warn("failed to parse epm event: %s" % obj)

        # pull all non-deleted endpoints from database for node and create
        # delete event for them
        elif job.data["status"] == "inactive":
            event_ts = time.time()  # set same event time for all delete events
            logger.debug("%s inactive, removing current endpoints from db"%dn)
            db_key = {
                "fabric": self.fabric,
                "node": job.data["node"],
                "events.0.status": { "$ne": "deleted"}
            }
            with self.app.app_context():
                db = self.app.mongo.db
                for h in db.ep_history.find(db_key,{"events":{"$slice":1}}):
                    delete_jobs = ep_get_delete_jobs(h, self.overlay_vnid,
                        event_ts=event_ts)  
                    if delete_jobs is None:
                        logger.warn("failed to get delete_jobs for %s" % h)
                    else:
                        jobs+= delete_jobs
        else:
            logger.warn("invalid status received: %s" % job.data["status"])
            return

        self.requeue_job(jobs) 
        return

def ep_get_delete_jobs(h, overlay_vnid, event_ts=None):
    """ from provided ep_history entry, create one or more ep_analyze jobs
        to delete the corresponding event
        return list of jobs or None on error
    """
    jobs = []
    if event_ts is None: event_ts = time.time()
    try:
        logger.debug("ep_get_delete_jobs for node-%s,vnid-%s,addr-%s" % (
            h["node"], h["vnid"], h["addr"]))
        # pod-id doesn't matter for delete event, manually set it to 1 
        dn = "topology/pod-1/node-%s/sys" % h["node"]
        event = h["events"][0]
        classname = ""
        edn = "%s/ctx-[vxlan-%s]" % (dn, event["vrf"])
        rwdn = ""
        if h["type"] == "mac":
            classname = "epmMacEp"
            edn = "%s/bd-[vxlan-%s]/db-ep/mac-%s"%(edn, event["bd"], h["addr"])
        elif h["type"] == "ip":
            classname = "epmIpEp"
            edn = "%s/db-ep/ip-[%s]" % (edn, h["addr"])
            if len(event["rw_mac"])>0:
                rwdn = "%s/ctx-[vxlan-%s]/bd-[vxlan-%s]"%(dn, event["vrf"], 
                    event["rw_bd"])
                if "vlan" in event["encap"]: rwdn+= "/vlan-[%s]"%event["encap"]
                elif "vxlan" in event["encap"]: rwdn+="/vxlan-[%s]" % (
                    event["encap"])
                elif len(event["encap"]) == 0: pass
                else:
                    logger.debug("unexpected encap: %s" % h)
                    return None
                rwdn+= "/db-ep/mac-%s/rsmacEpToIpEpAtt-[%s]"%(event["rw_mac"], 
                    edn)
        else:
            logger.warn("skipping ep with invalid type"%h)
            return

        # add job for epmRsMacEpToIpEpAtt for epmIpEp deletes
        if len(rwdn)>0:
            subclassname = "epmRsMacEpToIpEpAtt"
            obj = {subclassname:{"attributes":{"dn":rwdn,"status":"deleted"}}}
            key = ept_utils.parse_epm_event(subclassname, obj, overlay_vnid, 
                ts=event_ts)
            if key is not None:
                # epmRsMacEpToIpEpAtt set 'addr' from mac to ip attribute
                jkey={"type":key["type"],"addr":key["ip"],"vnid":key["vnid"]}
                jobs.append(EPJob("ep_analyze", jkey, ts=key["ts"],data=key))
            else:
                logger.warn("failed to parse epm event: %s"%obj)
                return None

        # create delete for mac or ip endpoint
        obj = {classname:{"attributes":{"dn":edn,"status":"deleted"}}}
        key = ept_utils.parse_epm_event(classname,obj,overlay_vnid, ts=event_ts)
        if key is not None:
            jkey = {"type": key["type"],"addr": key["addr"],"vnid": key["vnid"]}
            jobs.append(EPJob("ep_analyze",jkey,ts=key["ts"],data=key))
        else:
            logger.warn("failed to parse epm event: %s"%obj)
            return None
    except KeyError as e:
        logger.warn("ep_get_delete_job failed on %s as key %s is missing"%(h,e))
        return None
    except Exception as e:
        logger.error(traceback.format_exc())
        return None
    # return delete jobs
    return jobs

def ep_get_local_state(db, fabric, key):
    """ return list of nodes that currently see the endpoint as local,
        each with:
            fabric(str): fabric name
            vnid(str): endpoint BD vnid (for mac) or VRF vnid (for IP)
            addr(str): endpoint mac or ip address
            type(str): 'ip' or 'mac'
            node(str): node-id where endpoint is currently learned
            ifId(str): interface (vpc-id for vpc endpoints)
            encap(str): encapulation where endpoint is currently learned
            pcTag(str): pcTag where endpoint is currently learned
            rw_bd(str): rewrite BD for IP endpoints
            rw_mac(str): rewrite MAC for IP endpoints
            flags(str): EPM flags
        return None on error
    """
    if "addr" not in key or "vnid" not in key:
        logger.error("missing required attribute key or vnid: %s" % key)
        return None

    # rely on some of the ep_worker functions
    worker = EPWorker(None, None, None, fabric, 0, 0)
    all_local = []
    last_local_node = None
    db_key = {"fabric":fabric, "vnid":key["vnid"], "addr":key["addr"]}
    for h in db.ep_history.find(db_key):
        if "events" not in h or len(h["events"])==0: continue
        l = h["events"][0]
        if l is not None and "flags" in l and "status" in l and \
            l["status"]!="deleted" and ept_utils.ep_is_local(l["flags"]):
            n = h["node"]
            if "vpc-attached" in l["flags"]:
                pn = worker.get_peer_node(h["node"])
                if pn is None or pn is "":
                    logger.warn("failed to find vpc peer for %s" % h["node"])
                    return None
                n = "%s" % get_vpc_domain_id(n, pn)
            if last_local_node is None or last_local_node!=n:
                all_local.append({
                    "fabric": fabric, "vnid":key["vnid"], "addr":key["addr"],
                    "type": h["type"], "node":n, "ifId":l["ifId"], 
                    "encap":l["encap"], "pcTag":l["pcTag"], "rw_bd":l["rw_bd"],
                    "rw_mac":l["rw_mac"], "flags": l["flags"],
                    "vnid_name": l["vnid_name"] if "vnid_name" in l else "",
                    "epg_name": l["epg_name"] if "epg_name" in l else ""
                })
                last_local_node = n
    return all_local

def clear_fabric_endpoint(db, fabric, key, onodes, batch_size=32, timeout=30):
    """ clear endpoint from fabric on provided list of nodes. To clear endpoint
        on all leaf nodes, add node with value 0 to list
        Args:
            fabric - fabric name
            key - dict containing 'addr', 'vnid', and 'type'
            onodes - list of nodes to clear endpoint
            batch_size - number of concurrent processes to start at a time
            timeout - max running for single process to complete clear operation

        returns dict indexed by node id with following attributes:
            ret: {"success": bool, "details": ""},
            oob: out-of-band management address
            id: node-id,
            vlan: pi vlan for mac endpoint
            vrf: vrf name mapping to vnid for ip endpoint
        returns None on failure
    """
    from multiprocessing import Process as mProcess
    from multiprocessing import Queue as mQueue

    # rely on some of the ep_worker functions 
    # (setup default logger to utils.log)
    worker = EPWorker(None, None, None, fabric, 0, 0)
    ept_utils.setup_logger(logger, quiet=True)

    logger.debug("clear_fabric_endpoint on nodes %s for key %s" % (onodes,key))
    if "addr" not in key or "vnid" not in key or "type" not in key:
        logger.error("missing required attribute type, addr, or vnid: %s" % key)
        return None
    if key["type"]!="mac" and key["type"]!="ip":
        logger.warn("invalid key type '%s'" % key["type"])
        return None
    if type(onodes) is not list:
        logger.warn("nodes must be a list, received %s" % (str(type(onodes))))
        return None

    # set an error on all nodes return update dictionary
    def set_node_error(nodes, error):
        logger.warn(error)
        for n in nodes: nodes[n]["ret"]["details"] = error
        return nodes
    
    # get base return object for node
    def get_base(node_id):
        return {
            "ret": {"success": False, 
                "details":"Node not found or not active in the fabric"},
            "address": None,    # address (oob, inb, or tep address) to access
            "oob": None,        # node ipv4 OOB address
            "inb": None,        # node ipv6 address
            "tep": None,        # node inband-TEP address
            "id": node_id,      # node-id
            "vrf": None,        # (ip only) vrf name mapping to vnid 
            "vlan": None,       # (mac only) PI vlan mapping to vnid 
            "is_local": None,   # (mac only) ep is local or XR entry
            "encap": None,      # (mac only) vlan encap for local learn
            "dn": None,         # (mac only) dn for ep learn
        }

    all_nodes_set = False
    nodes = {}
    for n in onodes: 
        try:
            if type(n) is not str and type(n) is not unicode and \
                type(n) is not int: 
                node_id = "%s" % (str(type(n)))
                nodes[node_id] = get_base(node_id)
                continue
            elif int(n) == 0: all_nodes_set = True
            else: nodes[n] = get_base(n)
        except ValueError as e:
            nodes[n] = get_base(n)
            nodes[n]["ret"]["details"] = "Invalid node-id %s" % n

    # get apic config (containing ssh credentials) first.  if incomplete stop
    config = ept_utils.get_apic_config(fabric)
    if config is None:
        emsg = "error accessing fabric '%s' settings"
        if all_nodes_set and len(nodes) == 0: nodes[""] = get_base("")
        return set_node_error(nodes, emsg)
    if len(config["ssh_username"])==0 or len(config["ssh_password"])==0:
        emsg = "ssh credentials required to clear endpoints. Add the "
        emsg+= "appropriate credentials under the %s monitor settings"%(fabric)
        if all_nodes_set and len(nodes) == 0: nodes[""] = get_base("")
        return set_node_error(nodes, emsg)

    # first, get list of OOB IPs for each node (ipv4 only for now) and exclude
    # any non-leaf nodes
    one_node_found = False
    for h in db.ep_nodes.find({"fabric":fabric}):
        if h["id"] in nodes:
            if h["state"] != "in-service": continue
            elif h["role"] != "leaf":
                msg = "skipping node:%s with role:%s"%(h["id"],h["role"])
                logger.debug(msg)
                nodes[h["id"]]["ret"]["details"] = msg
                continue
        elif all_nodes_set and h["role"] == "leaf" and \
            h["state"] == "in-service":
                nodes[h["id"]] = get_base(h["id"])
        else:
            # skip invalid node 
            continue

        # set various inband/out-of-band/tep address
        nodes[h["id"]]["oob"] = h["oobMgmtAddr"]
        nodes[h["id"]]["inb"] = h["inbMgmtAddr"]
        nodes[h["id"]]["tep"] = h["address"]
        nodes[h["id"]]["address"] = {
            "oobMgmtAddr": h["oobMgmtAddr"],    
            "inbMgmtAddr": h["inbMgmtAddr"],
            "address": h["address"]
        }.get(config["ssh_access_method"], "address")

        # verify address is configured (defaults to 0.0.0.0)
        if nodes[h["id"]]["address"] == "0.0.0.0":
            if config["ssh_access_method"] == "address":
                msg = "Invalid TEP address: %s. "%nodes[h["id"]]["address"]
                msg+= "Ensure the node is discovered/active on the fabric."
            else:
                msg="Invalid %s address: %s"%(config["ssh_access_method"],
                    nodes[h["id"]]["address"])
                msg+=". Ensure a valid address is configured under the "
                msg+="mgmt tenant."
            logger.debug(msg)
            nodes[h["id"]]["ret"]["details"] = msg
            # clear the 'address' value since it is invalid
            nodes[h["id"]]["address"] = None
            continue
        one_node_found = True
        logger.debug("adding %s with addr %s (mode:%s) to valid nodes" % (
            h["id"],nodes[h["id"]]["address"], config["ssh_access_method"]))

    # if type is IP, then get mapping of vnid to vrf name
    if key["type"] == "ip":
        names = worker.get_vnid_name(key["vnid"])
        if names is None or names["vnid_name"] is None or \
            len(names["vnid_name"])==0:
            emsg = "failed to determine vrf name for vnid %s"%key["vnid"]
            return set_node_error(nodes, emsg)
        r1 =re.search("tn-(?P<tn>[^/]+)/ctx-(?P<ctx>[^/]+)",names["vnid_name"])
        if r1 is None:
            emsg = "failed to parse vrf name: %s" % names["vnid_name"]
            return set_node_error(nodes, emsg)
        vrf = "%s:%s" % (r1.group("tn"), r1.group("ctx"))
        logger.debug("mapping vnid to %s = %s " % (names["vnid_name"], vrf))
        for n in nodes: 
            if nodes[n]["address"] is not None: nodes[n]["vrf"] = vrf

    # if type is MAC, then get mapping of vnid to PI vlan
    # (1) determine if endpoint is known on node and 
    # (2) if known, map vlan encap to PI vlan
    else:
        # get MAC endpoint from all nodes in single query
        qtf = "eq(epmMacEp.addr,\"%s\")" % (key["addr"])
        session = ept_utils.refresh_session(fabric)
        if session is None:
            emsg = "failed to connect to APIC for epmMacEp state"
            return set_node_error(nodes, emsg)
        logger.debug("getting current state of %s on all nodes" % key["addr"])
        js = ept_utils.get_class(session, "epmMacEp", queryTargetFilter=qtf)
        if js is None:
            emsg = "failed to get current epmMacEp state for vnid:%s mac:%s"%(
                key["vnid"], key["addr"])
            return set_node_error(nodes, emsg)
        logger.debug("received %s objects from epmMacEp refresh" % len(js))
        # loop through each mac and add to node if in interesting 'nodes'
        for obj in js:
            classname = obj.keys()[0]
            mkey = ept_utils.parse_epm_event(classname,obj,worker.overlay_vnid)
            if mkey is None:
                logger.warn("failed to parse epm event: %s" % obj)
                continue
            if "/db-ep/mac-" not in mkey["dn"]:
                logger.warn("invalid epmMacEp dn: %s" % (mkey["dn"]))
                continue
            if mkey["vnid"] == key["vnid"] and mkey["node"] in nodes:
                node = nodes[mkey["node"]]
                node["dn"] = mkey["dn"]
                node["is_local"] = ept_utils.ep_is_local(mkey["flags"])
                if "encap" in mkey: node["encap"] = mkey["encap"]
           
        # get PI vlan for endpoint 
        for node_id in nodes:
            node = nodes[node_id]
            if node["address"] is None: continue  # skip invalid nodes
            if node["is_local"] is None:
                emsg = "%s vnid:%s not currently learned on node-%s" % (
                    key["addr"], key["vnid"], node["id"])
                node["ret"]["details"] = emsg
                logger.debug(emsg)
                continue
            # do query for l2Bd or vlanCktEp to determine PI vlan
            dn = node["dn"].split("/db-ep")[0]
            logger.debug("getting PI vlan for %s" % dn)
            js = ept_utils.get_dn(session, dn)
            if js is None:
                logger.debug("failed to get %s" % dn)
                node["ret"]["details"]="failed to map vlan, %s is None"%dn
                continue
            if len(js) == 0:
                logger.debug("dn %s not found" % dn)
                node["ret"]["details"] = "failed to map vlan, %s not found"%dn
                continue
            #logger.debug("returned object: %s" % ept_utils.pretty_print(js))
            classname = js.keys()[0]
            if "attributes" not in js[classname]: 
                logger.debug("attributes not found in %s object" % classname)
                node["ret"]["details"]="failed to map vlan, invalid %s object"%(
                                    classname)
                continue
            attr = js[classname]["attributes"]
            if "id" not in attr:
                logger.debug("id not found in %s attributes" % classname)
                node["ret"]["details"]="failed to map vlan, %s id not found"%(
                                    classname)
                continue
            logger.debug("mapped PI vlan for node-%s to vlan-%s" % (node["id"],
                attr["id"]))
            node["vlan"] = attr["id"]

    # at this point we have vrf name or PI vlan mapping for each valid node
    # create a new process and execute clear_node_endpoint
    work = []
    for node_id in nodes:
        node = nodes[node_id]
        if (key["type"] == "ip" and node["vrf"] is not None) or \
            (key["type"] == "mac" and node["vlan"] is not None):
            work.append(node) 
    if len(work) == 0:
        logger.debug("no valid nodes found to execute clear_endpoints")
        return nodes

    logger.debug("creating %s clear_endpoint jobs with batch size of %s" % (
        len(work), batch_size))
    proxy_hostname = None
    if config["ssh_access_method"] == "address": 
        proxy_hostname = config["apic_hostname"]
    while len(work)>0:
        workers = {}
        while len(workers)<batch_size and len(work)>0:
            node = work.pop()
            workers[node["id"]] = {
                "id": node["id"],
                "rQ": mQueue(),
                "node": node,
                "process": None,
                "key": { "type": key["type"], "addr": key["addr"],
                        "vrf": node["vrf"], "vlan": node["vlan"]},
            }
            p = mProcess(target=clear_node_endpoint, kwargs={
                "rQ": workers[node["id"]]["rQ"],
                "proxy_hostname": proxy_hostname,
                "hostname": node["address"],
                "username": config["ssh_username"],
                "password": config["ssh_password"],
                "key": workers[node["id"]]["key"]
            })
            workers[node["id"]]["process"] = p
        # start all workers in batch
        for wid in workers:
            w = workers[wid]
            w["process"].start()
            logger.debug("start clear_endpoint pid(%s) on node-%s with key %s"%(
                w["process"].pid, wid, w["key"]))
        # wait up to timeout for workers to complete
        start_time = time.time()
        while True:
            all_complete = True
            for wid in workers:
                w = workers[wid]
                if w["process"].is_alive(): 
                    all_complete = False
                    break
            if all_complete:
                logger.debug("all (%s) workers have completed" % len(workers))
                break
            if start_time + timeout > time.time(): time.sleep(0.1)
            else:
                logger.debug("some workers still running after timeout: %f" % (
                    timeout))
                break
        # get return code from all workers.  If worker is running, terminate it
        for wid in workers:
            w = workers[wid]
            if w["process"].is_alive():
                logger.debug("manually killing clear_endpoint on node-%s" % (
                    w["id"]))
                ept_utils.terminate_process(w["process"])
                emsg="failed to complete clear job within timeout:%ss"%timeout
                w["node"]["ret"]["details"] = emsg
            else:
                try:
                    rjob = w["rQ"].get_nowait()
                    w["node"]["ret"] = rjob.data
                except Empty:
                    logger.debug("worker node-%s has empty rQ" % wid)
                    emsg = "no return status received from clear job"
                    w["node"]["ret"]["details"] = emsg

    # each clear_node_endpoint return job updates nodes[ret] dictionary
    # at this point, only need to return nodes dict
    return nodes

def clear_node_endpoint(**kwargs):
    """ ssh to node with provided hostname and credentials and clear endpoint
        return EPJob on rQ with data containing success/details attributes  

        kwargs must contain:
            rQ - multiprocess queue to return result
            proxy_hostname - ip/hostname to proxy/jump to before ssh to host
            hostname - ip/hostname of device to access
            username - ssh username 
            password - ssh password
            key - dictionary with following attributes
                type: 'ip' or 'mac'
                addr: ip/mac to clear
                vlan: PI vlan on node for type 'mac'
                vrf: vrf name for type 'ip'
    """
    from ..tools.connection import Connection   
    rQ = kwargs.get("rQ", None)
    proxy_hostname = kwargs.get("proxy_hostname", None)
    hostname = kwargs.get("hostname", None)
    username = kwargs.get("username", None)
    password = kwargs.get("password", None)
    key = kwargs.get("key", None)
    ret = {
        "success": False,
        "details": ""
    }   
    rjob = EPJob("inform", {}, data=ret)
    if rQ is None or hostname is None or username is None or password is None \
        or key is None:
        logger.warn("one or more required arguments not provided")
        return

    # validate key before attempting to clear endpoint
    for a in ["vrf", "vlan", "addr", "type"]:
        if a not in key:
            logger.warn("key missing required attribute: %s" % a)
            ret["details"] = "key missing required attribute: %s" % a
            return rQ.put(rjob)
    if key["type"]!="mac" and key["type"]!="ip":
        logger.warn("invalid key type '%s'" % key["type"])
        ret["details"] = "invalid key type '%s'" % key["type"]
        return rQ.put(rjob)

    # if provided hostname is http/https url, exact just the hostname
    r1 = re.search("^http[s]://(?P<h>[^/]+)", hostname)
    if r1 is not None:
        logger.debug("extracting '%s' from url '%s'" % (r1.group("h"),
            hostname))
        hostname = r1.group("h")
    if proxy_hostname is not None:
        r2 = re.search("^http[s]://(?P<h>[^/]+)", proxy_hostname)
        if r2 is not None:
            logger.debug("extracting '%s' from url '%s'"%(r2.group("h"),
                proxy_hostname))
            proxy_hostname = r2.group("h")

    # attempt to ssh to provided hostname 
    if ept_utils.SIMULATION_MODE: c = ept_utils.CONNECTION_SIMULATOR
    elif proxy_hostname is not None: c = Connection(proxy_hostname)
    else: c = Connection(hostname)
    c.username = username
    c.password = password
    if not c.login(max_attempts=2, timeout=5):
        logger.debug("failed to login to node %s via %s" % (c.hostname,
            c.protocol))
        ret["details"] = "failed to login to node %s via %s" % (c.hostname,
            c.protocol)
        return rQ.put(rjob)
    logger.debug("successfully logged into %s via %s"%(c.hostname, c.protocol))

    # if this was a proxy, need to issue ssh commands to login to actual host
    # assumes apic for inband-tep mode with sshpass function present
    if proxy_hostname is not None:
        logger.debug("proxying to actual host: %s" % hostname)
        cmd = "ssh -l %s %s" % (username, hostname)
        if not c.remote_login(cmd, max_attempts=2, timeout=5):
            logger.debug("failed to login to node %s via ssh(proxy)"%hostname)
            ret["details"]="failed to login to node %s via ssh(proxy)"%hostname
            return rQ.put(rjob)

    # clear endpoint
    cmd = 'vsh -c "clear system internal epm endpoint key'
    if key["type"] == "ip":
        cmd+= ' vrf %s ip %s"' % (key["vrf"], key["addr"])
    else: 
        cmd+= ' vlan %s mac %s"' % (key["vlan"], key["addr"])
    r = c.cmd(cmd)
    logger.debug("text result of clear command: %s" % c.output)
    if r!= "prompt": 
        logger.debug("error executing command: %s" % r)
        ret["details"] = "error executing clear command: %s" % cmd
        return rQ.put(rjob)
    # check for exec error in output, if not present then assume success
    if re.search("exec error", c.output, re.IGNORECASE):
        logger.debug("exec error while executing command: %s" % cmd)
        ret["details"] = "exec error while executing command: %s" % cmd
        return rQ.put(rjob)
    # successfully executed command
    logger.debug("successfully executed clear command: %s" % cmd)
    ret["success"] = True
    return rQ.put(rjob)
