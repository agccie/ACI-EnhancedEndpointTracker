
from ... utils import get_app_config
from ... utils import get_redis
from ... utils import get_db
from ... utils import pretty_print
from .. utils import email
from .. utils import execute_worker
from .. utils import syslog
from . common import CACHE_STATS_INTERVAL
from . common import HELLO_INTERVAL
from . common import MANAGER_WORK_QUEUE
from . common import TRANSITORY_DELETE
from . common import TRANSITORY_OFFSUBNET
from . common import TRANSITORY_STALE
from . common import TRANSITORY_STALE_NO_LOCAL
from . common import SUPPRESS_WATCH_OFFSUBNET
from . common import SUPPRESS_WATCH_STALE
from . common import WATCH_INTERVAL
from . common import WORKER_CTRL_CHANNEL
from . common import push_event
from . common import get_addr_type
from . common import get_vpc_domain_id
from . common import get_vrf_name
from . common import split_vpc_domain_id
from . common import wait_for_db
from . common import wait_for_redis
from . ept_cache import eptCache
from . ept_endpoint import eptEndpoint
from . ept_endpoint import eptEndpointEvent
from . ept_history import eptHistory
from . ept_history import eptHistoryEvent
from . ept_move import eptMove
from . ept_move import eptMoveEvent
from . ept_msg import MSG_TYPE
from . ept_msg import WORK_TYPE
from . ept_msg import eptEpmEventParser
from . ept_msg import eptMsg
from . ept_msg import eptMsgHello
from . ept_msg import eptMsgWork
from . ept_msg import eptMsgWorkEpmEvent
from . ept_msg import eptMsgWorkWatchMove
from . ept_msg import eptMsgWorkWatchOffSubnet
from . ept_msg import eptMsgWorkWatchStale
from . ept_offsubnet import eptOffSubnet
from . ept_offsubnet import eptOffSubnetEvent
from . ept_queue_stats import eptQueueStats
from . ept_settings import eptSettings
from . ept_stale import eptStale
from . ept_stale import eptStaleEvent

import copy
import json
import logging
import re
import threading
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class eptWorker(object):
    """ endpoint tracker worker node handles epm events to update various history tables and perform
        endpoint analysis for one or more fabrics.
    """

    def __init__(self, worker_id, role):
        self.worker_id = "%s" % worker_id
        self.role = role
        self.db = get_db(uniq=True, overwrite_global=True)
        self.redis = get_redis()
        # dict of eptWorkerFabric objects
        self.fabrics = {}
        # broadcast hello for any managers (registration and keepalives)
        self.hello_thread = None
        # update stats db at regular interval
        self.stats_thread = None
        # check execute_ts for watch events at regular interval
        self.watch_thread = None

        # watcher active keys where key is unique fabric+addr+vnid+node
        self.watch_stale = {}
        self.watch_offsubnet = {}

        # multithreading locks
        self.queue_stats_lock = threading.Lock()
        self.watch_stale_lock = threading.Lock()
        self.watch_offsubnet_lock = threading.Lock()

        # queues that this worker will listen on 
        self.queues = ["q0_%s" % self.worker_id, "q1_%s" % self.worker_id]
        self.queue_stats = {
            "q0_%s" % self.worker_id: eptQueueStats.load(proc=self.worker_id, 
                                                    queue="q0_%s" % self.worker_id),
            "q1_%s" % self.worker_id: eptQueueStats.load(proc=self.worker_id, 
                                                    queue="q1_%s" % self.worker_id),
            WORKER_CTRL_CHANNEL: eptQueueStats.load(proc=self.worker_id,
                                                    queue=WORKER_CTRL_CHANNEL),
            MANAGER_WORK_QUEUE: eptQueueStats.load(proc=self.worker_id,
                                                    queue=MANAGER_WORK_QUEUE),
            "total": eptQueueStats.load(proc=self.worker_id, queue="total"),
        }
        # initialize stats counters
        for k, q in self.queue_stats.items():
            q.init_queue()

        start_ts = time.time()
        self.cache_stats_time = start_ts
        self.hello_msg = eptMsgHello(self.worker_id, self.role, self.queues, start_ts)
        self.hello_msg.seq = 0

        # handlers registered based on configured role
        if self.role == "watcher":
            self.work_type_handlers = {
                WORK_TYPE.FLUSH_CACHE: self.flush_cache,
                WORK_TYPE.WATCH_NODE: self.handle_watch_node,
                WORK_TYPE.WATCH_MOVE: self.handle_watch_move,
                WORK_TYPE.WATCH_OFFSUBNET: self.handle_watch_offsubnet,
                WORK_TYPE.WATCH_STALE: self.handle_watch_stale,
            }
        else:
            self.work_type_handlers = {
                WORK_TYPE.FLUSH_CACHE: self.flush_cache,
                WORK_TYPE.EPM_IP_EVENT: self.handle_endpoint_event,
                WORK_TYPE.EPM_MAC_EVENT: self.handle_endpoint_event,
                WORK_TYPE.EPM_RS_IP_EVENT: self.handle_endpoint_event,
            }

    def __repr__(self):
        return self.worker_id

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        try:
            wait_for_redis(self.redis)
            wait_for_db(self.db)
            self.send_hello()
            self.update_stats()
            if self.role == "watcher":
                self.execute_watch()
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        finally:
            if self.hello_thread is not None:
                self.hello_thread.cancel()
            if self.watch_thread is not None:
                self.watch_thread.cancel()
            if self.stats_thread is not None:
                self.stats_thread.cancel()

    def _run(self):
        """  start hello thread for registration notifications/keepalives and wait on work """
        # first check/wait on redis and mongo connection, then start hello thread
        logger.debug("[%s] listening for jobs on queues: %s", self, self.queues)
        while True: 
            (q, data) = self.redis.blpop(self.queues)
            if q in self.queue_stats:
                self.increment_stats(q, tx=False)
            try:
                msg = eptMsg.parse(data) 
                logger.debug("[%s] msg on q(%s): %s", self, q, msg)

                if msg.msg_type == MSG_TYPE.WORK:
                    if msg.wt in self.work_type_handlers:
                        self.check_fabric_cache(msg)
                        self.work_type_handlers[msg.wt](msg)
                    else:
                        logger.warn("unsupported work type: %s", msg.wt)
                elif msg.msg_type == MSG_TYPE.FLUSH_FABRIC:
                    self.flush_fabric(fabric=msg.data["fabric"])
                else:
                    logger.warn("unsupported worker msg type: %s", msg.msg_type)

            except Exception as e:
                logger.debug("failure occurred on msg from q: %s, data: %s", q, data)
                logger.error("Traceback:\n%s", traceback.format_exc())

    def increment_stats(self, queue, tx=False, count=1):
        # update stats queue
        with self.queue_stats_lock:
            if queue in self.queue_stats:
                if tx:
                    self.queue_stats[queue].total_tx_msg+= count
                    self.queue_stats["total"].total_tx_msg+= count
                else:
                    self.queue_stats[queue].total_rx_msg+= count
                    self.queue_stats["total"].total_rx_msg+= count

    def update_stats(self):
        # update stats at regular interval for all queues
        with self.queue_stats_lock:
            for k, q in self.queue_stats.items():
                q.collect(qlen = self.redis.llen(k))

        # set timer to recollect at next collection interval
        self.stats_thread = threading.Timer(eptQueueStats.STATS_INTERVAL, self.update_stats)
        self.stats_thread.daemon = True
        self.stats_thread.start()

    def send_msg(self, msg):
        """ send one or more eptMsgWork objects to worker via manager work queue 
            note, only main thread uses this operation so no need for lock at this point
        """
        if isinstance(msg, list):
            work = [m.jsonify() for m in msg]
            if len(work) == 0:
                # rpush requires at least one event, if msg is empty list then just return
                return
            self.redis.rpush(MANAGER_WORK_QUEUE, *work)
            self.increment_stats(MANAGER_WORK_QUEUE, tx=True, count=len(work))
        else:
            self.redis.rpush(MANAGER_WORK_QUEUE, msg.jsonify())
            self.increment_stats(MANAGER_WORK_QUEUE, tx=True)

    def send_hello(self):
        """ send hello/keepalives at regular interval, this also serves as registration """
        self.hello_msg.seq+= 1
        logger.debug(self.hello_msg)
        self.redis.publish(WORKER_CTRL_CHANNEL, self.hello_msg.jsonify())
        self.increment_stats(WORKER_CTRL_CHANNEL, tx=True)

        # print cache status for performance monitoring at regular interval
        ts = time.time()
        if CACHE_STATS_INTERVAL > 0 and ts - self.cache_stats_time > CACHE_STATS_INTERVAL:
            self.cache_stats_time = ts
            # in case fabric size changes in another thread
            fabrics = self.fabrics.keys()
            logger.debug("collecting cache statistics for %s caches", len(fabrics))
            for f in fabrics:
                if f in fabrics: 
                    self.fabrics[f].cache.log_stats()

        self.hello_thread = threading.Timer(HELLO_INTERVAL, self.send_hello)
        self.hello_thread.daemon = True
        self.hello_thread.start()

    def flush_fabric(self, fabric):
        """ flush only requires removing fabric from local fabrics, manager will handle removing any
            pending work from queue.  If this is a watcher, then also need to purge any watch events
            for this fabric.
        """
        logger.debug("[%s] flush fabric: %s", self, fabric)
        self.fabrics.pop(fabric, None)
        if self.role == "watcher":
            pop = []
            with self.watch_offsubnet_lock:
                for (key, msg) in self.watch_offsubnet:
                    if msg.fabric == fabric: pop.append(key)
                for k in pop: self.watch_offsubnet.pop(k, None)
            logger.debug("[%s] %s events removed from watch_offsubnet", self, len(pop))
            with self.watch_stale_lock:
                pop = []
                for (key, msg) in self.watch_stale:
                    if msg.fabric == fabric: pop.append(key)
                for k in pop: self.watch_stale.pop(k, None)
            logger.debug("[%s] %s events removed from watch_stale", self, len(pop))

    def flush_cache(self, msg):
        """ receive flush cache work containing cache and optional object name """
        logger.debug("flush cache fabric: %s, data: %s", msg.fabric, msg.data)
        if "cache" in msg.data and "name" in msg.data:
            if msg.fabric in self.fabrics:
                name = msg.data["name"]
                if len(name) == 0: 
                    name = None
                self.fabrics[msg.fabric].cache.handle_flush(msg.data["cache"], name=name)
            else:
                logger.debug("fabric %s not currently in cache", msg.fabric)
        else:
            logger.warn("invalid flush cache message")

    def check_fabric_cache(self, msg):
        """ create eptWorkerFabric object for this fabric if not already known """
        if msg.fabric not in self.fabrics:
            self.fabrics[msg.fabric] = eptWorkerFabric(msg.fabric)

    def handle_endpoint_event(self, msg):
        """ handle EPM endpoint event """

        # update endpoint history table and determine based on event if analysis is required
        analysis_required = self.update_endpoint_history(msg)

        # we no longer care what the original msg event type. However, we need to maintain the 
        # correct key (fabric, vnid, addr, node) and to ensure that addr is pointing to correct
        # value for EPM_RS_IP_EVENTs. Also, we need to update type to 'ip'.
        if msg.wt == WORK_TYPE.EPM_RS_IP_EVENT:
            msg.addr = msg.ip
            msg.type = "ip"
        # use msg fields to get last event for endpoint across all nodes for analysis
        projection = {
            "node": 1,
            "watch_stale_ts":1,         # will embed value into events.0
            "watch_offsubnet_ts": 1,    # will embed value into events.0
            "events": {"$slice": 4}     # offsubnet/stale dup check needs to see if obj was deleted
        }
        flt = {
            "fabric": msg.fabric,
            "vnid": msg.vnid,
            "addr": msg.addr,
        }
        per_node_history_events = {}    # one entry per node, indexed by node-id
        for h in self.db[eptHistory._classname].find(flt, projection):
            events = []
            for event in h["events"]:
                events.append(eptHistoryEvent.from_dict(event))
            # embed watch_ts into events.0
            if len(events) > 0:
                events[0].watch_stale_ts = h["watch_stale_ts"]
                events[0].watch_offsubnet_ts = h["watch_offsubnet_ts"]
                per_node_history_events[h["node"]] = events

        # update ept_endpoint with local event. Return last locals events for move analyze
        update_local_result = self.update_local(msg, per_node_history_events)

        # perform move/offsubnet/stale analysis
        if analysis_required: 
            if self.fabrics[msg.fabric].settings.analyze_move:
                if update_local_result.analyze_move:
                    self.analyze_move(msg, update_local_result.local_events)
                else:
                    logger.debug("skipping analyze move since update_local produced no update")
            if self.fabrics[msg.fabric].settings.analyze_offsubnet:
                self.analyze_offsubnet(msg, per_node_history_events, update_local_result)
            if self.fabrics[msg.fabric].settings.analyze_stale:
                self.analyze_stale(msg, per_node_history_events, update_local_result)

    def update_endpoint_history(self, msg):
        """ push event into eptHistory table and determine if analysis is required """
        # already have basic info logged when event was received (fabric, wt, node, vnid, addr, ip)
        # let's add ts, status, flags, ifId, pctag, vrf, bd, encap for full picture
        logger.debug("%s %.3f: vrf:0x%x, bd:0x%x, pcTag:0x%x, ifId:%s, encap:%s, flags(%s):[%s]",
                msg.status, msg.ts, msg.vrf, msg.bd, msg.pcTag, msg.ifId, msg.encap, len(msg.flags),
                ",".join(msg.flags))

        cache = self.fabrics[msg.fabric].cache
        is_local = "local" in msg.flags
        is_deleted = msg.status == "deleted"
        is_modified = msg.status == "modified"
        is_created = msg.status == "created"
        is_rs_ip_event = (msg.wt == WORK_TYPE.EPM_RS_IP_EVENT)
        is_ip_event = (msg.wt == WORK_TYPE.EPM_IP_EVENT)
        is_mac_event = (msg.wt == WORK_TYPE.EPM_MAC_EVENT)

        # will need to calcaulte remote node and ifId_name (defaults to ifId)
        remote = 0
        ifId_name = msg.ifId
        tunnel = None
        tunnel_flags = ""

        # independent of local or remote, if po is in ifId, then try to determine ifId_name
        if "po" in msg.ifId:
            # map ifId_name to port-channel policy name
            intf_name = cache.get_pc_name(msg.node, msg.ifId)
            if len(intf_name) > 0: 
                logger.debug("mapping ifId_name %s to %s", msg.ifId, intf_name)
                ifId_name = intf_name
            # if local, map interface to vpc-id if mapping exists. The vpc-attached flag should also 
            # be checked but for now we'll look only if mapping exists
            if is_local:
                vpc_id = cache.get_pc_vpc_id(msg.node, msg.ifId)
                if vpc_id > 0:
                    logger.debug("mapping ifId %s to vpc-%s", msg.ifId, vpc_id)
                    msg.ifId = "vpc-%s" % vpc_id
        # for tunnels, need to record tunnel_flags within history so do unconditional remap
        elif "tunnel" in msg.ifId:
            tunnel = cache.get_tunnel_remote(msg.node, msg.ifId, return_object=True)
            if tunnel is not None:
                tunnel_flags = tunnel.flags
                # for VL, endpoint is local and interface is a tunnel. Remap local interface from 
                # tunnel to VL destination
                if is_local and tunnel.encap == "vxlan":
                    logger.debug("mapping ifId %s to vl-%s", msg.ifId, tunnel.dst)
                    msg.ifId = "vl-%s" % tunnel.dst

        # determine remote node for this event if it is a non-deleted XR event
        if not is_local and not is_rs_ip_event and not is_deleted:
            if "cached" in msg.flags or "vtep" in msg.flags or msg.ifId=="unspecified":
                logger.debug("skipping remote map of cached/vtep/unspecified endpoint")
            elif "peer-attached" in msg.flags or "peer-attached-rl" in msg.flags:
                # if endpoint is peer-attached then remote is peer node, tunnel ifId should also
                # point to remote node but we'll give epm some slack if flag is set
                remote = cache.get_peer_node(msg.node)
            elif tunnel is not None:
                remote = tunnel.remote

        # add names to msg object and remote value to msg object
        setattr(msg, "vnid_name", cache.get_vnid_name(msg.vnid))
        setattr(msg, "epg_name", cache.get_epg_name(msg.vrf, msg.pcTag) if msg.pcTag>0 else "")
        setattr(msg, "remote", remote)
        setattr(msg, "ifId_name", ifId_name)
        setattr(msg, "tunnel_flags", tunnel_flags)

        # eptHistoryEvent representing current received event
        event = eptHistoryEvent.from_msg(msg)

        # get last event from eptHistory, use direct db access for projection and speed
        projection = {"events": {"$slice": 1}}
        flt = {
            "fabric": msg.fabric,
            "node": msg.node,
            "vnid": msg.vnid,
            "addr": msg.ip if is_rs_ip_event else msg.addr
        }
        last_event = self.db[eptHistory._classname].find_one(flt, projection)
        if last_event is None:
            logger.debug("new endpoint on node %s", msg.node)
            if not is_created:
                logger.debug("ignorning deleted/modified event for non-existing entry")
                return False
            # add new entry to db with most recent msg as the only event
            eptHistory(fabric=msg.fabric, node=msg.node, vnid=msg.vnid, addr=msg.addr, 
                    type=msg.type, count=1, events=[event.to_dict()]).save()

            # no analysis required for new event if:
            #   1) new event is epmRsMacEpToIpEpAtt (rewrite info without epmIpEp info)
            #   2) new event is epmIpEp and is local (missing epmRsMacEpToIpEpAtt info)
            if is_rs_ip_event:
                logger.debug("no analysis for new epmRsMacEpToIpEpAtt with no epmIpEp")
                return False
            elif is_local and is_ip_event:
                logger.debug("no analysis for new epmIpEp with no epmRsMacEpToIpEpAtt")
                return False
            else:
                logger.debug("new endpoint event on node %s requires analysis", msg.node)
                return True

        # eptHistoryEvent representing last event in db
        last_event = eptHistoryEvent.from_dict(last_event["events"][0])

        # a few more events that can be ignored
        if last_event.classname == event.classname:
            # ignore if db entry is more recent than event and classname for update is the same
            if last_event.ts > event.ts:
                logger.debug("current event is less recent than eptHistory event (%.3f < %.3f)",
                    event.ts, last_event.ts)
                return False
            # ignore if modify event received if last_event is deleted
            if last_event.status=="deleted" and (is_deleted or is_modified):
                logger.debug("ignore deleted/modified event for existing deleted entry")
                return False

        # special handling required for epmRsMacEpToIpEpAtt
        if is_rs_ip_event:
            # merge fields in event with last_event and update rw_mac and rw_bd values
            # note that status field is also merged (i.e., if object is deleted but a create event
            # is received for epmRsMacEpToIpEpAtt, then update occurs to rewrite info but status 
            # remains deleted)
            event.rw_mac = msg.addr
            event.rw_bd = msg.bd
            # for rw_mac and rw_bd to 0 if this is a delete rs_ip_event
            if is_deleted:
                event.rw_mac = ""
                event.rw_bd = 0
            for a in ["status", "remote", "pctag", "flags", "tunnel_flags", "encap", "intf_id", 
                "intf_name", "epg_name", "vnid_name"]:
                setattr(event, a, getattr(last_event, a))
            # need to recalculate local after merge
            is_local = "local" in event.flags
            if last_event.rw_mac != event.rw_mac or last_event.rw_bd != event.rw_bd:
                logger.debug("rewrite info updated from [bd:%s,mac:%s] to [bd:%s,mac:%s]", 
                    last_event.rw_bd, last_event.rw_mac, event.rw_bd, event.rw_mac)
                self.fabrics[msg.fabric].push_event(eptHistory._classname, flt, event.to_dict())
                if is_deleted:
                    logger.debug("no analysis required for delete to rewrite info")
                    return False
                elif not is_local:
                    logger.debug("no analysis required for rewrite update to XR endpoint")
                    return False
                else:
                    logger.debug("analysis required for rewrite update to local endpoint")
                    return True
            else:
                logger.debug("no update detected for eptHistory from rs_ip_event")
                return False

        # always merge rw_mac and rw_bd with previous entry as it is only updated by 
        # epmRsMacEpToIpAtt events that were already handled.
        if is_ip_event:
            event.rw_mac = last_event.rw_mac
            event.rw_bd = last_event.rw_bd

        # compare entry with previous entry to determine if a change has occured. If this is a 
        # deleted event, then add a delete entry while maintaining the rewrite info for epmIpEp.
        # If modified event, then merge result only changes values in modify event. If create, then
        # add full entry without merge
        update = False
        if is_created:
            # determine if any attribute has changed, if so push the new event
            for a in ["remote", "pctag", "flags", "encap", "intf_id"]:
                if getattr(last_event, a) != getattr(event, a):
                    logger.debug("node-%s '%s' updated from %s to %s", msg.node, a, 
                        getattr(last_event,a), getattr(event, a))
                    update = True
        elif is_deleted:
            # no comparision needed, rw info already merged, simply add the delete event
            # requirement to preserve vnid_name even on delete, therefore always merge w/ last_event
            setattr(event, "vnid_name", getattr(last_event, "vnid_name"))
            update = True
        elif is_modified:
            # all attributes will always be present even if not in the original modified event
            # therefore, we need to compare only non-default values and merge other values with 
            # last_event.

            # perform merge first on default values
            if event.remote == 0: 
                event.remote = last_event.remote
            if event.pctag == 0: 
                event.pctag = last_event.pctag
            for a in ["flags","tunnel_flags","encap","intf_id","intf_name","epg_name","vnid_name"]:
                if len(getattr(event, a)) == 0:
                    setattr(event, a, getattr(last_event, a))
            # need to recalculate local after merge
            is_local = "local" in event.flags
            # perform comparison of interesting attributes
            for a in ["remote", "pctag", "flags", "encap", "intf_id"]:
                if getattr(event, a) != getattr(last_event, a):
                    logger.debug("node-%s '%s' updated from %s to %s", msg.node, a, 
                        getattr(last_event, a), getattr(event, a))
                    update = True
        else:
            logger.warn("unsupported event status: %s", event.status)
            return False

        # if update occurred, push event to db
        if update:
            self.fabrics[msg.fabric].push_event(eptHistory._classname, flt, event.to_dict())
            # special case where update does not require analysis
            if is_ip_event and is_local and event.rw_bd == 0:
                logger.debug("no analysis for update to local IP endpoint with no rewrite info")
                return False
            else:
                logger.debug("update requires analysis")
                return True
        else:
            logger.debug("no update detected for eptHistory")
            return False

    def update_local(self, msg, per_node_history_event):
        """ update/add local entries to ept_endpoint table and return list of most recent
            fabric-wide complete local events (where complete requires rewrite info for ip endpoints)
            -   calculates where endpoint is local relevant to all nodes in the fabric. Note, the
                endpoint may be local on multiple nodes for vpc scenario, transistory event, or
                misconfig.  If currently local on multiple non-vpc nodes, then use latest event as
                source-of-truth.  
            -   if local event is different from eptEndpoint recent local, then add entry to 
                eptEndpoint events. 
            -   if previous event was a delete and current event is create with timestamp less than 
                transitory time, then overwrite the delete with the create

            return eptWorkerUpdateLocalResult object
        """
        ret = eptWorkerUpdateLocalResult()
        # get last local event from ept_endpoint
        projection = {
            "fabric": 1,
            "vnid": 1,
            "addr": 1,
            "is_stale": 1,
            "is_offsubnet": 1,
            "events": {"$slice": 2}
        }
        flt = {     
            "fabric": msg.fabric,
            "vnid": msg.vnid,
            "addr": msg.addr,
        }
        endpoint = self.db[eptEndpoint._classname].find_one(flt, projection)
        if endpoint is not None and len(endpoint["events"])>0:
            ret.exists = True
            ret.is_offsubnet = endpoint["is_offsubnet"]
            ret.is_stale = endpoint["is_stale"]
            ret.local_events = [eptEndpointEvent.from_dict(e) for e in endpoint["events"]]
            last_event = ret.local_events[0]
        else:
            # always create an eptEndpoint object for the endpoint even if no local events are 
            # ever created for it. Without eptEndpoint object then eptHistory total endpoints will
            # be out of sync. This is common scenario for vip/cache/svi/loopback endpoints that may
            # never have rw info and thus never 'complete local'
            if endpoint is None:
                endpoint_type = get_addr_type(msg.addr, msg.type)
                eptEndpoint(fabric=msg.fabric, vnid=msg.vnid, addr=msg.addr,type=endpoint_type,
                    first_learn={"status":"created"}).save()
            last_event = None

        # determine current complete local event
        local_event = None
        local_node = None
        for node in per_node_history_event:
            if len(per_node_history_event[node])>0:
                event = per_node_history_event[node][0]
                if "local" in event.flags:
                    # logger.debug("local check node 0x%04x: %s", node, event)
                    # ensure that rewrite info is set for ip endpoints
                    if msg.type=="mac" or (event.rw_bd > 0 and len(event.rw_mac) > 0):
                        if local_event is None or local_event.ts < event.ts:
                            local_event = event
                            local_node = node

        # if local_event is none then entry is XR on all nodes or deleted on all nodes
        if local_event is None:
            # need to add a delete event if entry currently exists within db and not deleted
            logger.debug("endpoint is XR or deleted on all nodes")
            if last_event is not None and last_event.node > 0:
                local_event = eptEndpointEvent.from_dict({
                    "ts":msg.ts, 
                    "status":"deleted",
                    "vnid_name": last_event.vnid_name       # maintain vnid_name even on delete
                })
                logger.debug("adding delete event to endpoint table: %s", local_event)
                self.fabrics[msg.fabric].push_event(eptEndpoint._classname,flt,local_event.to_dict())
                ret.local_events.insert(0, local_event)
                ret.analyze_move = True
            else:
                logger.debug("ignoring local delete event for XR/deleted/non-existing endpoint")
        else:
            # flags is eptHistory event but not eptNode event.  Need to maintain flags before casting
            local_event_flags = local_event.flags
            local_event = eptEndpointEvent.from_history_event(local_node, local_event)
            logger.debug("best local set to: %s", local_event)
            # map local_node to vpc value if this is a vpc
            if "vpc-attached" in local_event_flags:
                peer_node = self.fabrics[msg.fabric].cache.get_peer_node(local_event.node)
                if peer_node == 0:
                    logger.warn("failed to determine peer node for node 0x%04x", local_node)
                    return ret
                local_event.node = get_vpc_domain_id(local_event.node, peer_node)
            # create dict event to write to db
            db_event = local_event.to_dict()
            # if this is the first event, then set first_learn, count, and events in signle update
            if last_event is None:
                logger.debug("creating new entry in endpoint table: %s", local_event)
                self.db[eptEndpoint._classname].update_one(flt, {"$set":{
                    "first_learn": db_event,
                    "events": [db_event],
                    "count": 1,
                }})
                ret.local_events.insert(0, local_event)
                ret.analyze_move = True
                ret.exists = True
            else:
                # ensure that this entry is different and more recent
                updated = False
                ts_delta = local_event.ts - last_event.ts
                if ts_delta < 0:
                    logger.debug("current event is less recent than eptEndpoint event (%.3f < %.3f)",
                        local_event.ts, last_event.ts)
                else:
                    for a in ["node", "pctag", "encap", "intf_id", "rw_mac", "rw_bd"]:
                        if getattr(last_event, a) != getattr(local_event, a):
                            logger.debug("%s changed from '%s' to '%s'", a, getattr(last_event,a),
                                    getattr(local_event,a))
                            updated = True
                            #break  (can add a break later as only one attribute needs to change)
                if updated:
                    # if the previous entry was a delete and the current entry is not a delete, 
                    # then check for possible merge.
                    if last_event.node==0 and local_event.node>0 and ts_delta<=TRANSITORY_DELETE:
                        logger.debug("overwritting eptEndpoint [ts delta(%.3f) < %.3f] with: %s",
                            ts_delta, TRANSITORY_DELETE, local_event)
                        self.db[eptEndpoint._classname].update(flt, {"$set":{"events.0": db_event}})
                        ret.local_events[0] = local_event
                        ret.analyze_move = True
                    # push new event to eptEndpoint events  
                    else:
                        logger.debug("adding event to eptEndpoint: %s", local_event)
                        self.fabrics[msg.fabric].push_event(eptEndpoint._classname, flt, db_event)
                        ret.local_events.insert(0, local_event)
                        ret.analyze_move = True
                else:
                    logger.debug("no update detected for eptEndpoint")

        #logger.debug("eptEndpoint most recent local events(%s)", len(ret.local_events))
        #for i, l in enumerate(ret.local_events):
        #    logger.debug("event(%s): %s", i, l)
        # return last local endpoint events
        return ret

    def analyze_move(self, msg, last_local):
        """ analyze move event for endpoint. If last two local events are non-deleted different 
            events then consider it a move and add to eptMove table if not a duplicate of previous
            move.
            If a move occurs, create a watch job with WORK_TYPE.WATCH_MOVE and src/dst info for 
            notification. Note, if notification is disabled, then no need to create a watch event.
        """
        # need at least two non-deleted local events to compare
        if len(last_local)<2 or last_local[0].status=="deleted" or last_local[1].status=="deleted":
            logger.debug("skip move analysis, two non-deleted last local events required")
            return
        logger.debug("analyze move")
        
        update = False
        src = eptMoveEvent.from_endpoint_event(last_local[1])
        dst = eptMoveEvent.from_endpoint_event(last_local[0])
        move_event = {"src": src.to_dict(), "dst": dst.to_dict()}
        if not eptMoveEvent.is_different(src, dst):
            logger.debug("no move detected")
            return

        # need to ensure this move is not duplicate of existing entry. Unfortunately need to check
        # either src or dst is different from db results
        projection = {"events": {"$slice": 1}}
        flt = {
            "fabric": msg.fabric,
            "vnid": msg.vnid,
            "addr": msg.addr,
        }
        db_move = self.db[eptMove._classname].find_one(flt, projection)
        if db_move is None:
            logger.debug("new move detected (first)")
            endpoint_type = get_addr_type(msg.addr, msg.type)
            eptMove(fabric=msg.fabric, vnid=msg.vnid, addr=msg.addr, type=endpoint_type,
                    count=1, events=[move_event]).save()
        else:
            db_src = eptMoveEvent.from_dict(db_move["events"][0]["src"])
            db_dst = eptMoveEvent.from_dict(db_move["events"][0]["dst"])
            logger.debug("checking if move event is different from last eptMove event")
            move_uniq=eptMoveEvent.is_different(db_src,src) or eptMoveEvent.is_different(db_dst,dst)
            if not move_uniq:
                logger.debug("move is duplicate of previous move event")
                return
            logger.debug("new move detected")
            self.fabrics[msg.fabric].push_event(eptMove._classname, flt, move_event)

        if self.fabrics[msg.fabric].notification_enabled("move")["enabled"]:
            # send msg for WATCH_MOVE
            mmsg = eptMsgWorkWatchMove(msg.addr,"watcher",{},WORK_TYPE.WATCH_MOVE,fabric=msg.fabric)
            mmsg.vnid = msg.vnid
            mmsg.type = msg.type
            mmsg.src = move_event["src"]
            mmsg.dst = move_event["dst"]
            logger.debug("sending move event to watcher")
            self.send_msg(mmsg)
        else:
            logger.debug("move notification not enabled")


    def analyze_offsubnet(self, msg, per_node_history_events, update_local_result):
        """ analyze offsubnet
            perform offsubnet analysis across all nodes. Perform two eptHistory updates:
                1) clear is_offsubnet flag for this endpoint on all nodes
                2) set is_offsubnet flag for each node that is current is_offsbnet
            perform at most one eptEndpoint update:
                - if eptEndpoint.is_offsubnet flag is True but all nodes have is_offsubnet false,
                  then set eptEndpoint.is_offsubnet flag to false
                  Note, only watcher WATCH_OFFSUBNET sets eptEndpoint.is_offsubnet to true
                - current eptEndpoint.is_offsubnet value is within update_local_result.is_offsubnet
            for node that is_offsubnet, ensure that it is not duplicate of last eptOffSubnet event
                - for new/unique is_offsubnet then create WATCH_OFFSUBNET msg to handle
                  notifications, remediation, and insertion into eptOffsubnet table
        """ 
        if msg.type == "mac":
            logger.debug("skipping offsubnet analyze for mac event")
            return
        logger.debug("analyze offsubnet")
        offsubnet_nodes = {}    # indexed by node-id containing eptOffSubnetEvent
        for node in per_node_history_events:
            if len(per_node_history_events[node])>0:
                event = per_node_history_events[node][0]
                if event.pctag > 0 and event.status != "deleted":
                    #logger.debug("checking if [node:0x%04x 0x%06x, 0x%x, %s] is offsubnet", 
                    #    node, msg.vnid, event.pctag, msg.addr)
                    if self.fabrics[msg.fabric].cache.ip_is_offsubnet(msg.vnid,event.pctag,msg.addr):
                        offsubnet_nodes[node] = eptOffSubnetEvent.from_history_event(event)
        # update eptHistory is_offsubnet flags
        logger.debug("offsubnet on total of %s nodes", len(offsubnet_nodes))
        flt = {
            "fabric": msg.fabric,
            "vnid": msg.vnid,
            "addr": msg.addr,
        }
        self.db[eptHistory._classname].update_many(flt, {"$set":{"is_offsubnet":False}})
        for node in offsubnet_nodes:
            logger.debug("setting is_offsubnet to True for node 0x%04x", node)
            flt["node"] = node
            self.db[eptHistory._classname].update_one(flt, {"$set":{"is_offsubnet":True}})
        # clear eptEndpoint is_offsubnet flag if not currently offsubnet on any node
        if update_local_result.is_offsubnet and len(offsubnet_nodes) == 0:
            logger.debug("clearing eptEndpoint is_offsubnet flag")
            flt.pop("node",None)
            self.db[eptEndpoint._classname].update_one(flt, {"$set":{"is_offsubnet":False}})
        # check current offsubnet events against existing eptOffSubnet entry. here if there is an
        # existing eptOffSubnet event with same pctag and same remote entry AND there is no delete
        # after the timestamp within the per_node_event_history, then also consider this a dup
        projection = {"node":1, "watch_offsubnet_ts":1, "events": {"$slice":1}}
        if len(offsubnet_nodes)>0:
            duplicate_nodes = []
            # need to suppress rapid events if recent watch job created
            # last watch ts is embedded in per_node_history_events
            for node in offsubnet_nodes:
                if node in per_node_history_events:
                    delta = msg.ts - per_node_history_events[node][0].watch_offsubnet_ts
                    if delta != 0 and delta < SUPPRESS_WATCH_OFFSUBNET:
                        logger.debug("suppress watch_offsubnet for node 0x%04x (delta %.03f<%.03f)", 
                                node, delta, SUPPRESS_WATCH_OFFSUBNET)
                        if node not in duplicate_nodes:
                            duplicate_nodes.append(node)

            for db_obj in self.db[eptOffSubnet._classname].find(flt, projection):
                if db_obj["node"] in offsubnet_nodes and len(db_obj["events"])>0:
                    new_event = offsubnet_nodes[db_obj["node"]]
                    db_event = eptOffSubnetEvent.from_dict(db_obj["events"][0])
                    if db_event.remote == new_event.remote and db_event.pctag == new_event.pctag:
                        # check if this endpoint learn has been deleted and re-learned on node 
                        # since last eptOffSubnet event.  If so, clear is_duplicate flag
                        is_duplicate = True
                        for h_event in per_node_history_events[db_obj["node"]]:
                            if h_event.ts > db_event.ts and h_event.status == "deleted":
                                is_duplicate = False
                                break
                        if is_duplicate and db_obj["node"] not in duplicate_nodes:
                            logger.debug("offsubnet event for 0x%04x is dup/suppress",db_obj["node"])
                            duplicate_nodes.append(db_obj["node"])

            # remove duplicate_nodes from offsubnet_nodes list
            for node in duplicate_nodes:
                offsubnet_nodes.pop(node, None)
            # create work for WATCH_OFFSUBNET for each non-duplicate offsubnet events and set 
            # watch_offsubnet_ts for the node.  This is an extra db write but will suppress events
            # sent to watcher
            if len(offsubnet_nodes) > 0:
                msgs = []
                for node in offsubnet_nodes:
                    wmsg = eptMsgWorkWatchOffSubnet(msg.addr,"watcher",{},WORK_TYPE.WATCH_OFFSUBNET,
                            fabric=msg.fabric)
                    wmsg.ts = msg.ts
                    wmsg.node = node
                    wmsg.vnid = msg.vnid
                    wmsg.type = get_addr_type(msg.addr, msg.type)
                    wmsg.event = offsubnet_nodes[node].to_dict()
                    msgs.append(wmsg)
                    # mark watch ts for suppression of future events
                    flt["node"] = node
                    self.db[eptHistory._classname].update_one(flt, {"$set":{
                        "watch_offsubnet_ts":msg.ts
                    }})
                logger.debug("sending %s offsubnet events to watcher", len(msgs))
                self.send_msg(msgs)

    def analyze_stale(self, msg, per_node_history_events, update_local_result):
        """ analyze stale 
            stale analysis ensures that all nodes are pointing to expected the node. The 'expected' 
            node is the one with the current local learn. Nodes with XR entries can also have a 
            tunnel with proxy flag set (which indicates proxy lookup to spine) or point to a node 
            which currently has bounce flag set AND pointing toward correct node.

            if a node is claiming the endpoint as local and it is not the same node previously
            calculated as the current local node, then this is indication of the following:
                - a transient event that will be fixed up shortly by next event on websocket
                - loss of events on websocket subscription 
                    (would invaliate entire app if epm subscription is unreliable)
                - a coop update miss on the leaf causing multiple leafs to have the endpoint 
                  programmed locally. There are a few bugs where this can occur
            This app assumes the last event received is the most accurate state so we will consider 
            multiple local as a stale event if enabled within settings (multiple_local_stale)

            If not is_stale on any node but eptEndpoint entry has is_stale set, then clear the flag
            on eptEndpoint.  Else, for each node that has is_stale set and is not duplicate of 
            previous eptStale event, create a WATCH_STALE job to handle notification, remedation, 
            and insertion into eptStale table.

            stale analysis is skipped for mac endpoint. Although possible to have a mac endpoint that
            is stale, that has never been seen in production so we will skip that check to save some
            cycles on the app.

            stale analyis is also skipped on nodes with cached, vip, svi, psvi, vtep, static,
            bounce-to-proxy, or loopback flags set.
        """
        if msg.type == "mac":
            logger.debug("skipping stale analyze for mac event")
            return

        if len(update_local_result.local_events) == 0 or \
                update_local_result.local_events[0].node == 0:
            local_node = 0
            vpc_nodes = []
        else:
            local_node = update_local_result.local_events[0].node
            vpc_nodes = split_vpc_domain_id(local_node)
            if vpc_nodes[1] == 0:
                vpc_nodes.remove(1)
            if vpc_nodes[0] == 0:
                vpc_nodes.remove(0)

        stale_nodes = {}    # indexed by node with stale eptHistory event
        for node in per_node_history_events:
            h_event = per_node_history_events[node][0]
            event = eptStaleEvent.from_history_event(local_node, h_event)
            # only perform analysis on non-deleted entries
            if h_event.status != "deleted":
                if "bounce-to-proxy" in h_event.flags or \
                    "loopback" in h_event.flags or \
                    "vtep" in h_event.flags or \
                    "svi" in h_event.flags or \
                    "psvi" in h_event.flags or \
                    "cached" in h_event.flags or \
                    "static" in h_event.flags:
                    logger.debug("skipping stale analysis on node 0x%04x with flags: [%s]", node,
                        ",".join(h_event.flags))
                    continue
                # if this is a tunnel and tunnel flags have proxy or dci flags, then skip it:
                #   - proxy-acast-v4, proxy-acast-v6, proxy-acast-mac
                #   - dci-unicast    (remote pod DCI unicast)
                #   - dci-mcast-hrep (remote site mcast tep)
                # covers 
                if "proxy" in h_event.tunnel_flags or "dci" in h_event.tunnel_flags:
                    logger.debug("skipping stale analysis on node 0x%04x with tunnel flags: %s",
                        node, h_event.tunnel_flags)
                    continue
                if local_node > 0:
                    if "local" in h_event.flags:
                        # this node thinks the endpoint is local. If it matches local_node or is a 
                        # member within vpc_nodes then skip it
                        if node != local_node and node not in vpc_nodes:
                            logger.debug("node %s claiming local != node %s (%s)", node, local_node,
                                    vpc_nodes)
                            if self.fabrics[msg.fabric].settings.stale_multiple_local:
                                stale_nodes[node] = event
                            else:
                                logger.debug("ignroing stale_multiple_local")
                    else:
                        # ensure that this node has correct remote pointer or is pointing to a node
                        # with bounce and correct node pointer.  Need to come back and validate if
                        # bounce-to-proxy will actually bounce a frame, will revisit...
                        # NOTE, for vpc there's no way to know from flags whether the peer's pc is 
                        # down. Therefore, allow remote to point to vpc TEP or member nodes
                        if h_event.remote != local_node and h_event.remote not in vpc_nodes:
                            if h_event.remote in per_node_history_events:
                                remote_node_event = per_node_history_events[h_event.remote][0]
                                if remote_node_event.remote != local_node or (
                                    "bounce" not in remote_node_event.flags and \
                                    "bounce-to-proxy" not in remote_node_event.flags
                                    ):
                                    logger.debug("stale on %s to %s [flags [%s], to %s]", node, 
                                        h_event.remote, ",".join(remote_node_event.flags),
                                        remote_node_event.remote)
                                    stale_nodes[node] = event
                            else:
                                logger.debug("stale on %s to %s", node, h_event.remote)
                                stale_nodes[node] = event
                else:
                    # non-deleted event when endpoint is not currently learned within the fabric
                    if self.fabrics[msg.fabric].settings.stale_no_local:
                        logger.debug("stale on %s to %s (no local)", node, h_event.remote)
                        stale_nodes[node] = event
                    else:
                        logger.debug("ignoring stale_no_local")

        # update eptHistory is_stale flags
        logger.debug("stale on total of %s nodes", len(stale_nodes))
        flt = {
            "fabric": msg.fabric,
            "vnid": msg.vnid,
            "addr": msg.addr,
        }
        self.db[eptHistory._classname].update_many(flt, {"$set":{"is_stale":False}})
        for node in stale_nodes:
            logger.debug("setting is_stale to True for node 0x%04x", node)
            flt["node"] = node
            self.db[eptHistory._classname].update_one(flt, {"$set":{"is_stale":True}})
        # clear eptEndpoint is_stale flag if not currently stale on any node
        if update_local_result.is_stale and len(stale_nodes) == 0:
            logger.debug("clearing eptEndpoint is_stale flag")
            flt.pop("node",None)
            self.db[eptEndpoint._classname].update_one(flt, {"$set":{"is_stale":False}})

        # check current stale events against existing eptStale entry. here if there is an
        # existing eptStale event with same remote and expected remote AND there is no delete
        # after the timestamp within the per_node_event_history, then consider this a dup
        projection = {"node":1, "events": {"$slice":1}}
        if len(stale_nodes)>0:
            duplicate_nodes = []

            # need to suppress rapid events if recent watch job created
            # last watch ts is embedded in per_node_history_events
            for node in stale_nodes:
                if node in per_node_history_events:
                    delta = msg.ts - per_node_history_events[node][0].watch_stale_ts
                    if delta != 0 and delta < SUPPRESS_WATCH_STALE:
                        logger.debug("suppress watch_stale for node 0x%04x (delta %.03f<%.03f)", 
                                node, delta, SUPPRESS_WATCH_STALE)
                        if node not in duplicate_nodes:
                            duplicate_nodes.append(node)

            for db_obj in self.db[eptStale._classname].find(flt, projection):
                if db_obj["node"] in stale_nodes and len(db_obj["events"])>0:
                    new_event = stale_nodes[db_obj["node"]]
                    db_event = eptStaleEvent.from_dict(db_obj["events"][0])
                    if db_event.remote == new_event.remote and \
                        db_event.expected_remote == new_event.expected_remote:
                        # check if this endpoint learn has been deleted and re-learned on node 
                        # since last eptStale event.  If so, clear is_duplicate flag
                        is_duplicate = True
                        for h_event in per_node_history_events[db_obj["node"]]:
                            if h_event.ts > db_event.ts and h_event.status == "deleted":
                                is_duplicate = False
                                break
                        if is_duplicate and db_obj["node"] not in duplicate_nodes:
                            logger.debug("stale event for 0x%04x is dup/suppres",db_obj["node"])
                            duplicate_nodes.append(db_obj["node"])

            # remove duplicate_nodes from stale_nodes list
            for node in duplicate_nodes:
                stale_nodes.pop(node, None)
            # create work for WATCH_STALE for each non-duplicate stale events and set
            # watch_stale_ts for the node.  This is an extra db write but will suppress events
            # sent to watcher
            if len(stale_nodes) > 0:
                msgs = []
                for node in stale_nodes:
                    wmsg = eptMsgWorkWatchStale(msg.addr,"watcher",{},WORK_TYPE.WATCH_STALE,
                            fabric=msg.fabric)
                    wmsg.ts = msg.ts
                    wmsg.node = node
                    wmsg.vnid = msg.vnid
                    wmsg.type = get_addr_type(msg.addr, msg.type)
                    wmsg.event = stale_nodes[node].to_dict()
                    msgs.append(wmsg)
                    # mark watch ts for suppression of future events
                    flt["node"] = node
                    self.db[eptHistory._classname].update_one(flt, {"$set":{
                        "watch_stale_ts":msg.ts
                    }})
                logger.debug("sending %s stale events to watcher", len(msgs))
                self.send_msg(msgs)

    def handle_watch_node(self, msg):
        """ watch node triggered any time a node goes into non-active state.  When this occurs, a 
            delete job needs to be created for all current non-deleted history events for that node
            and requeued through manager process
        """
        if msg.status == "active":
            logger.debug("ignorning watch event for active node")
            return

        delete_msgs = []
        parser = self.fabrics[msg.fabric].ept_epm_parser
        flt = {
            "fabric": msg.fabric,
            "node": msg.node,
            "events.0.status": {"$ne": "deleted"},
        }
        projection = {
            "node": 1,
            "vnid": 1,
            "addr": 1,
            "type": 1,
        }
        for obj in self.db[eptHistory._classname].find(flt, projection):
            if obj["type"] == "mac":
                m = parser.get_delete_event("epmMacEp",obj["node"],obj["vnid"],obj["addr"],msg.ts)
                if m is not None:
                    delete_msgs.append(m)
            else:
                # create an epmRsMacEpToIpEpAtt and epmIpEp delete event
                m = parser.get_delete_event("epmRsMacEpToIpEpAtt", obj["node"], obj["vnid"], 
                        obj["addr"], msg.ts)
                if m is not None:
                    delete_msgs.append(m)
                m = parser.get_delete_event("epmIpEp", obj["node"], obj["vnid"], obj["addr"],msg.ts)
                if m is not None:
                    delete_msgs.append(m)

        # requeue delete msgs
        logger.debug("sending %s deletes for node 0x%04x", len(delete_msgs), msg.node)
        self.send_msg(delete_msgs)

    def handle_watch_move(self, msg):
        """ send proper move notifications if enabled """
        # build notification msg and execute notify send
        subject = "move detected for %s" % msg.addr
        txt = "move detected [fabric: %s, %s, addr: %s] from %s to %s" % (
            msg.fabric,
            msg.src["vnid_name"] if len(msg.src["vnid_name"])>0 else "vnid:%d" % msg.vnid,
            msg.addr,
            eptMoveEvent(**msg.src).notify_string(include_rw=(msg.type!="mac")),
            eptMoveEvent(**msg.dst).notify_string(include_rw=(msg.type!="mac")),
        )
        self.fabrics[msg.fabric].send_notification("move", subject, txt)

    def handle_watch_offsubnet(self, msg):
        """ recieves a eptMsgWorkWatchOffSubnet message and adds object to watch_offsubnet dict with 
            execute timestamp (xts) of current ts + TRANSITORY_OFFSUBNET timer. If object already
            exists it is overwrittent with the new watch event.
        """
        key = "%s%s%s%s" % (msg.fabric, msg.addr, msg.vnid, msg.node)
        msg.xts = msg.ts + TRANSITORY_OFFSUBNET
        with self.watch_offsubnet_lock:
            self.watch_offsubnet[key] = msg
        logger.debug("watch offsubnet added to dict with xts: %.03f", msg.xts)

    def handle_watch_stale(self, msg):
        """ recevie a eptMsgWorkWatchStale message and adds object to watch_stale dict with execute
            timestamp (xts) of current ts + TRANSITORY_STALE or TRANSITORY_STALE_NO_LOCAL timer.
            If object already exists it is overwritten with the new watch event.
        """
        key = "%s%s%s%s" % (msg.fabric, msg.addr, msg.vnid, msg.node)
        if msg.event["expected_remote"] == 0:
            msg.xts = msg.ts + TRANSITORY_STALE_NO_LOCAL
        else:
            msg.xts = msg.ts + TRANSITORY_STALE
        with self.watch_stale_lock:
            self.watch_stale[key] = msg
        logger.debug("watch stale added to dict with xts: %.03f", msg.xts)

    def execute_watch(self):
        """ check for watch events with execute ts ready and perform corresponding actions
            reset timer to perform event again at next WATCH_INTERVAL
        """
        self._execute_watch("offsubnet")
        self._execute_watch("stale")

        # set timer to trigger at next interval
        self.watch_thread = threading.Timer(WATCH_INTERVAL, self.execute_watch)
        self.watch_thread.daemon = True
        self.watch_thread.start()

    def _execute_watch(self, watch_type):
        """ loop through all events in watch_type dict. for each event with xts ready check if 
            watch_type (is_offsubnet/is_stale) value within corresponding eptHistory object is set.
            If true, update eptEndpoint (is_offsubnet/is_stale) attribute and then perform 
            configured notify and remediate actions.  Add object ept collection (no dup check here)
        """
        work = []               # tuple of (key, msg) of watch event that is ready

        if watch_type == "offsubnet":
            lock = self.watch_offsubnet_lock
            msgs = self.watch_offsubnet
            ept_db = eptOffSubnet
            ept_db_attr = "is_offsubnet"
            event_class = eptOffSubnetEvent
            remediate_attr = "auto_clear_offsubnet"
        elif watch_type == "stale":
            lock = self.watch_stale_lock
            msgs = self.watch_stale
            ept_db = eptStale
            ept_db_attr = "is_stale"
            event_class = eptStaleEvent
            remediate_attr = "auto_clear_stale"
        else:
            logger.error("unsupported watch type '%s'", watch_type)
            return

        ts = time.time()
        with lock:
            # get msg events that are ready, remove key from corresponding dict
            for k, msg in msgs.items():
                if msg.xts <= ts: work.append((k, msg))
            for (k, msg) in work: msgs.pop(k, None)

        if len(work) > 0:
            clear_cmds = []      # list of clear commands to execute in parallel
            logger.debug("execute %s ready watch %s events", len(work), watch_type)
            for (key, msg) in work:
                logger.debug("checking: %s", msg)
                flt = {
                    "fabric": msg.fabric,
                    "vnid": msg.vnid,
                    "addr": msg.addr,
                    "node": msg.node,
                }
                projection = {
                    ept_db_attr: 1
                }
                h = self.db[eptHistory._classname].find_one(flt, projection)
                if h is not None and h[ept_db_attr]: 
                    logger.debug("%s is true, updating eptEndpoint and pushing event", ept_db_attr)
                    # update eptEndpoint object 
                    self.db[eptHistory._classname].update_one(flt, {"$set":{ept_db_attr:True}})
                    # push event to db. Here, the only non-key value not present is 'type' which we
                    # will set as a key to allow proper upsert functionality if object does not 
                    # exists (upsert = no extra read!)
                    key = copy.copy(flt)
                    key["type"] = msg.type
                    event = event_class.from_dict(msg.event)
                    self.fabrics[msg.fabric].push_event(ept_db._classname, key, event.to_dict())
                    # send notification if enabled
                    subject = "%s event for %s" % (watch_type, msg.addr)
                    txt = "%s event [fabric: %s, %s, addr: %s] %s" % (
                        watch_type,
                        msg.fabric,
                        event.vnid_name if len(event.vnid_name)>0 else "vnid:%d" % msg.vnid,
                        msg.addr,
                        event.notify_string()
                    )
                    self.fabrics[msg.fabric].send_notification(watch_type, subject, txt)
                    # add to clear list if remediation is enabled
                    if getattr(self.fabrics[msg.fabric].settings, remediate_attr):
                        logger.debug("%s enabled, adding endpoint to clear list", remediate_attr)
                        cmd = "clear --fabric %s --pod %s --node %s --addr %s --vnid %s " % (
                                msg.fabric,
                                self.fabrics[msg.fabric].cache.get_pod_id(msg.node),
                                msg.node,
                                msg.addr,
                                msg.vnid)
                        if msg.type == "mac":
                            cmd+= "--addr_type mac"
                        else:
                            cmd+= "--addr_type ip --vrf_name \"%s\"" % get_vrf_name(event.vnid_name)
                        clear_cmds.append(cmd) 
            # perform clear action for all clear cmds
            if len(clear_cmds) > 0:
                logger.debug("executing %s clear endpoint commands", len(clear_cmds))
                for cmd in clear_cmds:
                    execute_worker(cmd)

class eptWorkerUpdateLocalResult(object):
    """ return object for eptWorker.update_loal method """
    def __init__(self):
        self.analyze_move = False       # an update requiring move analysis occurred
        self.local_events = []          # recent (0-3) local eptEndpointEvent objects
        self.is_offsubnet = False       # eptEndpoint object is currently offsubnet
        self.is_stale = False           # eptEndpoint object is currently stale
        self.exists = False             # eptEndpoint entry exists

class eptWorkerFabric(object):
    """ tracks cache and settings for each fabric actively being monitored """
    def __init__(self, fabric):
        self.fabric = fabric
        self.settings = eptSettings.load(fabric=fabric)
        self.cache = eptCache(fabric)
        self.db = get_db()
        # epm parser used with eptWorker for creating pseudo eevents
        self.ept_epm_parser = eptEpmEventParser(self.fabric, self.settings.overlay_vnid)
        # one time calculation for email address and syslog server (which requires valid port)
        self.email_address = self.settings.email_address
        self.syslog_server = self.settings.syslog_server
        self.syslog_port = self.settings.syslog_port
        if len(self.email_address) == 0: 
            self.email_address = None
        if len(self.syslog_server) == 0:
            self.syslog_server = None
            self.syslog_port = None

    def push_event(self, table, key, event):
        # wrapper to push an event to eptHistory events list
        if table == eptEndpoint._classname:
            return push_event(self.db[table], key, event, 
                    rotate=self.settings.max_endpoint_events)
        else:
            return push_event(self.db[table], key, event, 
                    rotate=self.settings.max_per_node_endpoint_events)

    def notification_enabled(self, notify_type):
        # return dict with email address, syslog server, syslog port for notify type. If not enabled,
        # then return None for each field.
        ret = {"enabled": False, "email_address": None, "syslog_server": None, "syslog_port": None}
        if notify_type == "move":
            attr = ("notify_move_email", "notify_move_syslog")
        elif notify_type == "stale":
            attr = ("notify_stale_email", "notify_stale_syslog")
        elif notify_type == "offsubnet":
            attr = ("notify_offsubnet_email", "notify_offsubnet_syslog")
        else:
            logger.warn("invalid notification type '%s", notify_type)
            return ret
        if getattr(self.settings, attr[0]):
            ret["enabled"] = True
            ret["email_address"] = self.email_address
        if getattr(self.settings, attr[1]):
            ret["enabled"] = True
            ret["syslog_server"] = self.syslog_server
            ret["syslog_port"] = self.syslog_port
        return ret

    def send_notification(self, notify_type, subject, txt):
        # send proper notifications for this fabric 
        notify = self.notification_enabled(notify_type)
        if notify["enabled"]:
            if notify["email_address"] is not None:
                email(
                    msg=txt,
                    subject=subject,
                    sender = get_app_config().get("EMAIL_SENDER", None),
                    receiver=notify["email_address"],
                )
            if notify["syslog_server"] is not None:
                syslog(txt, server=notify["syslog_server"], server_port=notify["syslog_port"])
        else:
            logger.debug("skipping send notification as '%s' is not enabled", notify_type)

