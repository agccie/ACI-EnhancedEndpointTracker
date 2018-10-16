
from ... utils import get_redis
from ... utils import get_db
from ... utils import pretty_print
from . common import CACHE_STATS_INTERVAL
from . common import HELLO_INTERVAL
from . common import MANAGER_WORK_QUEUE
from . common import TRANSITORY_DELETE
from . common import TRANSITORY_OFFSUBNET
from . common import TRANSITORY_STALE
from . common import TRANSITORY_STALE_NO_LOCAL
from . common import WORKER_CTRL_CHANNEL
from . common import push_event
from . common import get_vpc_domain_id
from . common import get_addr_type
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
        return push_event(self.db[table], key, event, rotate = self.settings.max_endpoint_events)

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

        # multithreading locks
        self.queue_stats_lock = threading.Lock()

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

        self.work_type_handlers = {
            WORK_TYPE.FLUSH_CACHE: self.flush_cache,
            WORK_TYPE.EPM_IP_EVENT: self.handle_endpoint_event,
            WORK_TYPE.EPM_MAC_EVENT: self.handle_endpoint_event,
            WORK_TYPE.EPM_RS_IP_EVENT: self.handle_endpoint_event,
            #WORK_TYPE.WATCH_NODE: self.handle_watch_node,
            WORK_TYPE.WATCH_MOVE: self.handle_watch_move,
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
            self.increment_stats(WORKER_WORK_QUEUE, tx=True, count=len(work))
        else:
            self.redis.rpush(MANAGER_WORK_QUEUE, msg.jsonify())
            self.increment_stats(WORKER_WORK_QUEUE, tx=True)

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
        """ handle EPM endpoint event
        """

        # create eptWorkerFabric object for this fabric if not already known
        if msg.fabric not in self.fabrics:
            self.fabrics[msg.fabric] = eptWorkerFabric(msg.fabric)

        # update endpoint history table and determine based on event if analysis is required
        analysis_required = self.update_endpoint_history(msg)
        
        if analysis_required: 
            # we no longer care what the original msg event type. However, we need to maintain the 
            # correct key (fabric, vnid, addr, node) and to ensure that addr is pointing to correct
            # value for EPM_RS_IP_EVENTs.
            msg.addr = msg.ip if (msg.wt == WORK_TYPE.EPM_RS_IP_EVENT) else msg.addr
            # use msg fields to get last event for endpoint across all nodes for analysis
            projection = {"node": 1, "events": {"$slice": 1}}
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
                per_node_history_events[h["node"]] = events

            # update ept_endpoint with local event. Return last locals events for move analyze
            (update, last_local) = self.update_local(msg, per_node_history_events)

            if self.fabrics[msg.fabric].settings.analyze_move:
                if update:
                    self.analyze_move(msg, last_local)
                else:
                    logger.debug("skipping analyze move since update_local produced no update")
            if self.fabrics[msg.fabric].settings.analyze_offsubnet:
                pass
            if self.fabrics[msg.fabric].settings.analyze_stale:
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
        is_deleted = msg.status == "deleted"
        is_modified = msg.status == "modified"
        is_created = msg.status == "created"
        is_rs_ip_event = (msg.wt == WORK_TYPE.EPM_RS_IP_EVENT)
        is_ip_event = (msg.wt == WORK_TYPE.EPM_IP_EVENT)
        is_mac_event = (msg.wt == WORK_TYPE.EPM_MAC_EVENT)

        # will need to calcaulte remote node and ifId_name (defaults to ifId)
        ifId_name = msg.ifId
        remote = 0

        # determine remote node for this event if it is a non-deleted XR event
        if not is_local and not is_rs_ip_event and not is_deleted:
            if "cached" in msg.flags or "vtep" in msg.flags or msg.ifId=="unspecified":
                logger.debug("skipping remote map of cached/vtep/unspecified endpoint")
            elif "peer-attached" in msg.flags or "peer-attached-rl" in msg.flags:
                # if endpoint is peer-attached then remote is peer node, tunnel ifId should also
                # point to remote node but we'll give epm some slack if flag is set
                remote = cache.get_peer_node(msg.node)
            elif "tunnel" not in msg.ifId:
                logger.debug("skipping remote map of XR non-tunnel interface (ok on modify)")
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
        setattr(msg, "epg_name", cache.get_epg_name(msg.vrf, msg.pcTag) if msg.pcTag>0 else "")
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
            for a in ["status", "remote", "pctag", "flags", "encap", "intf_id", "intf_name", 
                "epg_name", "vnid_name"]:
                setattr(event, a, getattr(last_event, a))
            # need to recalculate local after merge
            is_local = "local" in event.flags
            if last_event.rw_mac != event.rw_mac or last_event.rw_bd != event.rw_bd:
                logger.debug("rewrite info updated from [bd:%s,mac:%s] to [bd:%s,mac:%s]", 
                    last_event.rw_bd, last_event.rw_mac, event.rw_bd, event.rw_mac)
                self.fabrics[msg.fabric].push_event(eptHistory._classname, flt, event.to_dict())
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
            return tuple (
                update_occurred (bool),
                local (list of local endpoint events),
            )
            -   calculates where endpoint is local relevant to all nodes in the fabric. Note, the
                endpoint may be local on multiple nodes for vpc scenario, transistory event, or
                misconfig.  If currently local on multiple non-vpc nodes, then use latest event as
                source-of-truth.  
            -   if local event is different from eptEndpoint recent local, then add entry to 
                eptEndpoint events. 
            -   if previous event was a delete and current event is create with timestamp less than 
                transitory time, then overwrite the delete with the create
        """
        ret_list = []
        update_occurred = False
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
            ret_list = [eptEndpointEvent.from_dict(e) for e in endpoint["events"]]
            last_event = ret_list[0]
        else:
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
                ret_list.insert(0, local_event)
                update_occurred = True
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
                    return (False, ret_list)
                local_event.node = get_vpc_domain_id(local_event.node, peer_node)
            # create dict event to write to db
            db_event = local_event.to_dict()
            # if this is the first event, then create eptEndpoint object and set first_learn
            if last_event is None:
                logger.debug("creating new entry in endpoint table: %s", local_event)
                endpoint_type = get_addr_type(msg.addr, msg.type)
                eptEndpoint(fabric=msg.fabric, vnid=msg.vnid, addr=msg.addr, count=1, 
                    type=endpoint_type, first_learn=db_event, events=[db_event]).save()
                ret_list.insert(0, local_event)
                update_occurred = True
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
                        ret_list[0] = local_event
                        update_occurred = True
                    # push new event to eptEndpoint events  
                    else:
                        logger.debug("adding event to eptEndpoint: %s", local_event)
                        self.fabrics[msg.fabric].push_event(eptEndpoint._classname, flt, db_event)
                        ret_list.insert(0, local_event)
                        update_occurred = True
                else:
                    logger.debug("no update detected for eptEndpoint")

        # return last local endpoint events
        logger.debug("eptEndpoint most recent local events(%s)", len(ret_list))
        for i, l in enumerate(ret_list):
            logger.debug("event(%s): %s", i, l)
        return (update_occurred, ret_list)


    def analyze_move(self, msg, last_local):
        """ analyze move event for endpoint. If last two local events are non-deleted different 
            events then consider it a move and add to eptMove table if not a duplicate of previous
            move.
            If a move occurs, create a watch job with WORK_TYPE.WATCH_MOVE and src/dst info for 
            notification. Note, if notification is disabled, then no need to create a watch event.
        """
        # need at least two non-deleted local events to compare
        if len(last_local)<2 or last_local[0].status=="deleted" or last_local[1].status=="deleted":
            logger.debug("two non-deleted last local events required for move analysis")
            return
        
        move_compare_attributes = ["node", "intf_id", "pctag", "encap", "rw_mac", "rw_bd"]
        update = False
        src = eptMoveEvent.from_endpoint_event(last_local[1])
        dst = eptMoveEvent.from_endpoint_event(last_local[0])
        move_event = {"src": src.to_dict(), "dst": dst.to_dict()}
        for a in move_compare_attributes:
            if getattr(src, a) != getattr(dst, a):
                logger.debug("move: %s changed from '%s' to '%s'",a,getattr(src,a),getattr(dst,a))
                update = True
        if not update:
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
            move_uniq = False
            for a in move_compare_attributes:
                if getattr(db_src, a) != getattr(src, a) or getattr(db_dst, a) != getattr(dst, a):
                    move_uniq = True
                    break
            if not move_uniq:
                logger.debug("move is duplicate of previous move event")
                return
            logger.debug("new move detected")
            self.fabrics[msg.fabric].push_event(eptMove._classname, flt, move_event)

        if self.fabrics[msg.fabric].notification_enabled("move")["enabled"]:
            # send msg for WATCH_MOVE
            data = {
                "addr": msg.addr,
                "vnid": msg.vnid,
                "event": move_event
            }
            msg = eptMsgWork(msg.addr, "watcher", data, WORK_TYPE.WATCH_MOVE, fabric=msg.fabric)
            logger.debug("sending move event to watcher")
            self.send_msg(msg)
        else:
            logger.debug("move notification not enabled")


    def handle_watch_move(self, msg):
        # TODO
        pass






