
from ... utils import get_redis
from ... utils import get_db
from . common import CACHE_STATS_INTERVAL
from . common import HELLO_INTERVAL
from . common import WORKER_CTRL_CHANNEL
from . common import TRANSITORY_DELETE
from . common import TRANSITORY_OFFSUBNET
from . common import TRANSITORY_STALE
from . common import TRANSITORY_STALE_NO_LOCAL
from . common import wait_for_db
from . common import wait_for_redis
from . common import push_event
from . ept_cache import eptCache
from . ept_history import eptHistory
from . ept_history import eptHistoryEvent
from . ept_move import eptMove
from . ept_msg import MSG_TYPE
from . ept_msg import WORK_TYPE
from . ept_msg import eptMsg
from . ept_msg import eptMsgHello
from . ept_msg import eptMsgWork
from . ept_msg import eptMsgWorkEpmEvent
from . ept_offsubnet import eptOffSubnet
from . ept_queue_stats import eptQueueStats
from . ept_settings import eptSettings
from . ept_stale import eptStale

import json
import logging
import re
import threading
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class eptWorkerFabric(object):
    """ tracks cache and settings for each fabric actively being monitored """
    def __init__(self, fabric):
        self.fabric = fabric
        self.settings = eptSettings.load(fabric=fabric)
        self.cache = eptCache(fabric)
        self.db = get_db()

    def push_history_event(self, key, event):
        # wrapper to push an event to eptHistory events list
        return push_event(self.db[eptHistory._classname], key, event, 
                rotate = self.settings.max_endpoint_events)

class eptWorker(object):
    """ endpoint tracker worker node handles epm events to update various history tables and perform
        endpoint analysis for one or more fabrics.
    """

    def __init__(self, worker_id, role):
        self.worker_id = "%s" % worker_id
        self.role = role
        self.db = get_db()
        self.redis = get_redis()
        # dict of eptWorkerFabric objects
        self.fabrics = {}
        # broadcast hello for any managers (registration and keepalives)
        self.hello_thread = None
        # update stats db at regular interval
        self.stats_thread = None

        # queues that this worker will listen on 
        self.queues = ["q0_%s" % self.worker_id, "q1_%s" % self.worker_id]
        self.queue_stats_lock = threading.Lock()
        self.queue_stats = {
            "q0_%s" % self.worker_id: eptQueueStats.load(proc=self.worker_id, 
                                                    queue="q0_%s" % self.worker_id),
            "q1_%s" % self.worker_id: eptQueueStats.load(proc=self.worker_id, 
                                                    queue="q1_%s" % self.worker_id),
            WORKER_CTRL_CHANNEL: eptQueueStats.load(proc=self.worker_id,
                                                    queue=WORKER_CTRL_CHANNEL),
            "total": eptQueueStats.load(proc=self.worker_id, queue="total"),
        }
        # initialize stats counters
        for k, q in self.queue_stats.items():
            q.init_queue()

        self.hello_msg = eptMsgHello(self.worker_id, self.role, self.queues, time.time())
        self.hello_msg.seq = 0
        self.cache_stats_time = 0

        self.work_type_handlers = {
            WORK_TYPE.EPM_IP_EVENT: self.handle_endpoint_event,
            WORK_TYPE.EPM_MAC_EVENT: self.handle_endpoint_event,
            WORK_TYPE.EPM_RS_IP_EVENT: self.handle_endpoint_event,
            WORK_TYPE.WATCH_NODE: self.handle_watch_event,
            WORK_TYPE.FLUSH_CACHE: self.flush_cache,
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
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        finally:
            if self.hello_thread is not None:
                self.hello_thread.cancel()
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


    def increment_stats(self, queue, tx=False):
        # update stats queue
        with self.queue_stats_lock:
            if queue in self.queue_stats:
                if tx:
                    self.queue_stats[queue].total_tx_msg+= 1
                    self.queue_stats["total"].total_tx_msg+= 1
                else:
                    self.queue_stats[queue].total_rx_msg+= 1
                    self.queue_stats["total"].total_rx_msg+= 1

    def update_stats(self):
        # update stats at regular interval for all queues
        with self.queue_stats_lock:
            for k, q in self.queue_stats.items():
                q.collect(qlen = self.redis.llen(k))

        # set timer to recollect at next collection interval
        self.stats_thread = threading.Timer(eptQueueStats.STATS_INTERVAL, self.update_stats)
        self.stats_thread.daemon = True
        self.stats_thread.start()

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
            pending work from queue
        """
        logger.debug("[%s] flush fabric: %s", self, fabric)
        self.fabrics.pop(fabric, None)

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

    def handle_endpoint_event(self, msg):
        """ handle EPM endpoint event i
        
            -   calculates where endpoint is local relevant to all nodes in the fabric. Note, the
                endpoint may be local on multiple nodes for vpc scenario, transistory event, or
                misconfig.
                If local event is different from eptEndpoint recent local (and within transitory 
                timers), then add entry to eptEndpoint events.
            -   trigger analysis function for each analysis enabled (move, stale, offsubnet).

        
        """

        # create eptWorkerFabric object for this fabric if not already known
        if msg.fabric not in self.fabrics:
            self.fabrics[msg.fabric] = eptWorkerFabric(msg.fabric)

        # update endpoint history table and determine based on event if analysis is required
        analysis_required = self.update_endpoint_history(msg)
        
        if analysis_required: 
            # 
            if self.fabrics[msg.fabric].settings.analyze_move:
                pass
            if self.fabrics[msg.fabric].settings.analyze_stale:
                pass
            if self.fabrics[msg.fabric].settings.analyze_offsubnet:
                pass


    def update_endpoint_history(self, msg):
        """ push event into eptHistory table and determine if analysis is required """
        # already have basic info logged when event was received (fabric, wt, node, vnid, addr, ip)
        # let's add ts, status, flags, ifId, pctag, vrf, bd, encap for full picture
        logger.debug("%s %.3f: vrf:0x%x, bd:0x%x, pcTag:0x%x, ifId:%s, encap:%s, flags(%s):[%s]",
                msg.status, msg.ts, msg.vrf, msg.bd, msg.pcTag, msg.ifId, msg.encap, len(msg.flags),
                ",".join(msg.flags))

        cache = self.fabrics[msg.fabric].cache
        is_local = "local" in msg.flags
        is_rs_ip_event = (msg.wt == WORK_TYPE.EPM_RS_IP_EVENT)
        is_ip_event = (msg.wt == WORK_TYPE.EPM_IP_EVENT)
        is_mac_event = (msg.wt == WORK_TYPE.EPM_MAC_EVENT)

        # will need to calcaulte remote node and ifId_name (defaults to ifId)
        ifId_name = msg.ifId
        remote = 0

        # determine remote node for this event if its a non-deleted XR event
        if not is_local and not is_rs_ip_event and msg.status != "deleted":
            if "cached" in msg.flags or "vtep" in msg.flags or msg.ifId=="unspecified":
                logger.debug("skipping remote map of cached/vtep/unspecified endpoint")
            elif "peer-attached" in msg.flags or "peer-attached-rl" in msg.flags:
                # if endpoint is peer-attached then remote is peer node, tunnel ifId should also
                # point to remote node but we'll give epm some slack if flag is set
                remote = cache.get_peer_node(msg.node)
            elif "tunnel" not in msg.ifId:
                logger.debug("skipping remote map of XR non-tunnel interface")
            else:
                remote = cache.get_tunnel_remote(msg.node, msg.ifId)

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
        # for VL, endpoint is local and interface is a tunnel. Remap local interface from tunnel
        # to VL destination
        elif "tunnel" in msg.ifId and is_local:
            tunnel = cache.get_tunnel_remote(msg.node, msg.ifId, return_object=True)
            if tunnel is not None and tunnel.encap == "vxlan":
                logger.debug("mapping ifId %s to vl-%s", msg.ifId, tunnel.dst)
                msg.ifId = "vl-%s" % tunnel.dst

        # add names to msg object and remote value to msg object
        setattr(msg, "vnid_name", cache.get_vnid_name(msg.vnid))
        setattr(msg, "epg_name", cache.get_epg_name(msg.vrf, msg.pcTag))
        setattr(msg, "remote", remote)
        setattr(msg, "ifId_name", ifId_name)

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
            if event.status != "created":
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
                logger.debug("current event is less recent than db event (%.3f < %.3f)",
                    event.ts, last_event.ts)
                return False
            # ignore if modify event received and last_event is deleted
            if last_event.status=="deleted" and event.status=="deleted" or event.status=="modified":
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
            for a in ["status", "remote", "pctag", "flags", "encap", "intf_id", "intf_name", 
                "epg_name", "vnid_name"]:
                setattr(event, a, getattr(last_event, a))
            # need to recalculate local after merge
            is_local = "local" in event.flags
            if last_event.rw_mac != event.rw_mac or last_event.rw_bd != event.rw_bd:
                logger.debug("rewrite info updated from bd:%s,mac:%s to bd:%s,mac:%s", 
                    last_event.rw_bd, last_event.rw_mac, event.rw_bd, event.rw_mac)
                self.fabrics[msg.fabric].push_history_event(flt, event.to_dict())
                if event.status == "deleted":
                    logger.debug("no analysis required for delete to rewrite info")
                    return False
                elif not is_local:
                    logger.debug("no analysis required for rewrite update to XR endpoint")
                    return False
                else:
                    logger.debug("analysis required for rewrite update to local endpoint")
                    return True
            else:
                logger.debug("no update detected for endpoint")
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
        if event.status == "created":
            # determine if any attribute has changed, if so push the new event
            for a in ["remote", "pctag", "flags", "encap", "intf_id"]:
                if getattr(last_event, a) != getattr(event, a):
                    logger.debug("node-%s '%s' updated from %s to %s", msg.node, a, 
                        getattr(last_event,a), getattr(event, a))
                    update = True
        elif event.status == "deleted":
            # no comparision needed, rw info already merged, simply add the delete event
            update = True
        elif event.status == "modified":
            # all attributes will always be present even if not in the original modified event
            # therefore, we need to compare only non-default values and merge other values with 
            # last_event.

            # perform merge first on default values
            if event.remote == 0: 
                event.remote = last_event.remote
            if event.pctag == 0: 
                event.pctag = last_event.pctag
            for a in ["flags", "encap", "intf_id", "intf_name", "epg_name", "vnid_name"]:
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
            self.fabrics[msg.fabric].push_history_event(flt, event.to_dict())
            # special case where update does not require analysis
            if is_ip_event and is_local and event.rw_bd == 0:
                logger.debug("no analysis for update to local IP endpoint with no rewrite info")
                return False
            else:
                logger.debug("update requires analysis")
                return True
        else:
            logger.debug("no update detected for endpoint")
            return False



    def handle_watch_event(self, msg):
        # TODO
        pass






