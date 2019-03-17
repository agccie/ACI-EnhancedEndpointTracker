
from ... utils import get_redis
from ... utils import get_db
from .. utils import execute_worker
from .. utils import raise_interrupt
from .. utils import register_signal_handlers
from . common import CACHE_STATS_INTERVAL
from . common import HELLO_INTERVAL
from . common import MANAGER_WORK_QUEUE
from . common import RAPID_CALCULATE_INTERVAL
from . common import TRANSITORY_DELETE
from . common import TRANSITORY_OFFSUBNET
from . common import TRANSITORY_RAPID
from . common import TRANSITORY_STALE
from . common import TRANSITORY_STALE_NO_LOCAL
from . common import SUPPRESS_WATCH_OFFSUBNET
from . common import SUPPRESS_WATCH_STALE
from . common import SUBSCRIBER_CTRL_CHANNEL
from . common import WATCH_INTERVAL
from . common import WORKER_CTRL_CHANNEL
from . common import MAX_SEND_MSG_LENGTH
from . common import BackgroundThread
from . common import db_alive
from . common import get_addr_type
from . common import get_vpc_domain_id
from . common import parse_vrf_name
from . common import split_vpc_domain_id
from . common import wait_for_db
from . common import wait_for_redis
from . ept_endpoint import eptEndpoint
from . ept_endpoint import eptEndpointEvent
from . ept_history import eptHistory
from . ept_history import eptHistoryEvent
from . ept_move import eptMove
from . ept_move import eptMoveEvent
from . ept_msg import MSG_TYPE
from . ept_msg import WORK_TYPE
from . ept_msg import eptMsg
from . ept_msg import eptMsgBulk
from . ept_msg import eptMsgHello
from . ept_msg import eptMsgSubOp
from . ept_msg import eptMsgWork
from . ept_msg import eptMsgWorkEpmEvent
from . ept_msg import eptMsgWorkWatchMove
from . ept_msg import eptMsgWorkWatchOffSubnet
from . ept_msg import eptMsgWorkWatchRapid
from . ept_msg import eptMsgWorkWatchStale
from . ept_offsubnet import eptOffSubnet
from . ept_offsubnet import eptOffSubnetEvent
from . ept_rapid import eptRapid
from . ept_remediate import eptRemediate
from . ept_queue_stats import eptQueueStats
from . ept_stale import eptStale
from . ept_stale import eptStaleEvent
from . ept_worker_fabric import eptWorkerFabric
from . mo_dependency_map import dependency_map

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
        threading.currentThread().name = "main"
        logger.debug("init role %s id %s", role, worker_id)
        register_signal_handlers()
        self.worker_id = "%s" % worker_id
        self.role = role
        self.db = get_db(uniq=True, overwrite_global=True, write_concern=True)
        self.redis = get_redis()
        # dict of eptWorkerFabric objects
        self.fabrics = {}
        # broadcast hello for any managers (registration and keepalives)
        self.hello_thread = None
        # update stats db at regular interval
        self.stats_thread = None
        # check execute_ts for watch events at regular interval
        self.watch_thread = None

        # watcher active keys where key is unique fabric+addr+vnid+node (rapid excludes node)
        self.watch_stale = {}
        self.watch_offsubnet = {}
        self.watch_rapid = {}

        # multithreading locks
        self.queue_stats_lock = threading.Lock()
        self.watch_stale_lock = threading.Lock()
        self.watch_offsubnet_lock = threading.Lock()
        self.watch_rapid_lock = threading.Lock()
        self.manager_work_queue_lock = threading.Lock()

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
            SUBSCRIBER_CTRL_CHANNEL: eptQueueStats.load(proc=self.worker_id, 
                                                    queue=SUBSCRIBER_CTRL_CHANNEL),
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
                WORK_TYPE.WATCH_RAPID: self.handle_watch_rapid,
                WORK_TYPE.TEST_EMAIL: self.handle_test_email,
                WORK_TYPE.TEST_SYSLOG: self.handle_test_syslog,
                WORK_TYPE.SETTINGS_RELOAD: self.handle_settings_reload,
                WORK_TYPE.FABRIC_WATCH_PAUSE: self.handle_watch_pause,
                WORK_TYPE.FABRIC_WATCH_RESUME: self.handle_watch_resume,
                WORK_TYPE.STD_MO: self.handle_std_mo_event,
            }
        else:
            self.work_type_handlers = {
                WORK_TYPE.FLUSH_CACHE: self.flush_cache,
                WORK_TYPE.RAW: self.handle_raw_endpoint_event,
                WORK_TYPE.EPM_IP_EVENT: self.handle_endpoint_event,
                WORK_TYPE.EPM_MAC_EVENT: self.handle_endpoint_event,
                WORK_TYPE.EPM_RS_IP_EVENT: self.handle_endpoint_event,
                WORK_TYPE.DELETE_EPT: self.handle_endpoint_delete,
                WORK_TYPE.SETTINGS_RELOAD: self.handle_settings_reload,
                WORK_TYPE.FABRIC_EPM_EOF:  self.handle_epm_eof,
            }

    def __repr__(self):
        return self.worker_id

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        try:
            wait_for_redis(self.redis)
            wait_for_db(self.db)
            # start stats thread
            self.stats_thread = BackgroundThread(func=self.update_stats, name="worker-stats", 
                                                count=0, interval= eptQueueStats.STATS_INTERVAL)
            self.stats_thread.daemon = True
            self.stats_thread.start()
            # start hello thread
            self.hello_thread = BackgroundThread(func=self.send_hello, name="worker-hello", count=0,
                                                interval = HELLO_INTERVAL)
            self.hello_thread.daemon = True
            self.hello_thread.start()
            if self.role == "watcher":
                self.execute_watch()
                # watcher needs to trigger execute watch at regular interval
                self.watch_thread = BackgroundThread(func=self.execute_watch, name="watch", count=0,
                                                interval=WATCH_INTERVAL)
                self.watch_thread.daemon = True
                self.watch_thread.start()
            # start listening to redis channels/queues
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        finally:
            if self.hello_thread is not None:
                self.hello_thread.exit()
            if self.watch_thread is not None:
                self.watch_thread.exit()
            if self.stats_thread is not None:
                self.stats_thread.exit()
            if self.db is not None:
                self.db.client.close()
            if self.redis is not None and self.redis.connection_pool is not None:
                self.redis.connection_pool.disconnect()

    def _run(self):
        """ listen for work on redis queues """
        # first check/wait on redis and mongo connection, then start hello thread
        logger.debug("[%s] listening for jobs on queues: %s", self, self.queues)
        while True: 
            (q, data) = self.redis.blpop(self.queues)
            # to support msg type BULK, assume an array of messages received
            msg_list = []
            try:
                omsg = eptMsg.parse(data) 
                if omsg.msg_type == MSG_TYPE.BULK:
                    logger.debug("[%s] msg on q(%s): %s", self, q, omsg)
                    msg_list = omsg.msgs
                else:
                    msg_list = [omsg]
                # increment rx stats for received message
                if q in self.queue_stats:
                    self.increment_stats(q, tx=False, count=len(msg_list))
                for msg in msg_list:
                    # exception on one msg must not block processing of other messages in block
                    try:
                        logger.debug("[%s] msg on q(%s): %s", self, q, msg)
                        if msg.msg_type == MSG_TYPE.WORK:
                            if msg.wt in self.work_type_handlers:
                                # set msg.wf to current fabric eptWorkerFabric object
                                self.set_msg_worker_fabric(msg)
                                self.work_type_handlers[msg.wt](msg)
                            else:
                                logger.warn("unsupported work type: %s", msg.wt)
                        elif msg.msg_type == MSG_TYPE.FABRIC_START:
                            self.fabric_start(fabric=msg.data["fabric"])
                        elif msg.msg_type == MSG_TYPE.FABRIC_STOP:
                            self.fabric_stop(fabric=msg.data["fabric"])
                        else:
                            logger.warn("unsupported worker msg type: %s", msg.msg_type)
                    except Exception as e:
                        logger.debug("failed to execute msg %s", msg)
                        logger.error("Traceback:\n%s", traceback.format_exc())
            except Exception as e:
                logger.debug("failed to parse message from q: %s, data: %s", q, data)
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
        """ update stats at regular interval """
        # monitor db health prior to db updates
        if not db_alive(self.db):
            logger.error("db no longer reachable/alive")
            raise_interrupt()
            return
        # update stats at regular interval for all queues
        for k, q in self.queue_stats.items():
            with self.queue_stats_lock:
                q.collect(qlen = self.redis.llen(k))

    def send_msg(self, msg):
        """ send one or more eptMsgWork objects to worker via manager work queue 
            limit the number of messages sent at a time to MAX_SEND_MSG_LENGTH
        """
        if isinstance(msg, list):
            # break up msg into multiple blocks and send as single eptMsgBulk
            for i in range(0, len(msg), MAX_SEND_MSG_LENGTH):
                bulk = eptMsgBulk()
                bulk.msgs = [m for m in msg[i:i+MAX_SEND_MSG_LENGTH]]
                if len(bulk.msgs)>0:
                    with self.manager_work_queue_lock:
                        self.redis.rpush(MANAGER_WORK_QUEUE, bulk.jsonify())
                    self.increment_stats(MANAGER_WORK_QUEUE, tx=True, count=len(bulk.msgs))
        else:
            with self.manager_work_queue_lock:
                self.redis.rpush(MANAGER_WORK_QUEUE, msg.jsonify())
            self.increment_stats(MANAGER_WORK_QUEUE, tx=True)

    def send_flush(self, collection, name=None):
        """ send flush message to workers for provided collection """
        logger.debug("flush %s (name:%s)", collection._classname, name)
        # node addr of 0 is broadcast to all nodes of provided role
        data = {"cache": collection._classname, "name": name}
        msg = eptMsgWork(0, "worker", data, WORK_TYPE.FLUSH_CACHE)
        msg.qnum = 0    # highest priority queue
        self.send_msg(msg)

    def send_hello(self):
        """ send hello/keepalives at regular interval, this also serves as registration """
        self.hello_msg.seq+= 1
        #logger.debug(self.hello_msg)
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

    def fabric_start(self, fabric):
        """ start fabric to init cache and for watcher process, to set a start timestamp for the 
            fabric for extending transitory timers
        """
        # need to trigger a graceful stop for worker process if already cached
        self.fabric_stop(fabric)
        logger.debug("[%s] start fabric: %s", self, fabric)
        self.fabrics[fabric] = eptWorkerFabric(fabric)
        if self.role == "watcher":
            self.fabrics[fabric].start_session()

    def fabric_stop(self, fabric):
        """ stop only requires removing fabric from local fabrics, manager will handle removing any
            pending work from queue. If this is a watcher, then also need to purge any watch events
            for this fabric.
        """
        logger.debug("[%s] stop fabric: %s", self, fabric)
        old_wf = self.fabrics.pop(fabric, None)
        if old_wf is not None:
            old_wf.close()
        if self.role == "watcher":
            watches = [
                ("offsubnet", self.watch_offsubnet_lock, self.watch_offsubnet),
                ("stale", self.watch_stale_lock, self.watch_stale),
                ("rapid", self.watch_rapid_lock, self.watch_rapid),
            ]
            for (name, lock, d) in watches:
                pop = []
                with lock:
                    for (key, msg) in d.items():
                        if msg.fabric == fabric: 
                            pop.append(key)
                    for k in pop: 
                        d.pop(k, None)
                logger.debug("[%s] %s events removed from watch_%s", self, len(pop), name)

    def flush_cache(self, msg):
        """ receive flush cache work containing cache and optional object name """
        logger.debug("flush cache fabric: %s, data: %s", msg.fabric, msg.data)
        if "cache" in msg.data and "name" in msg.data:
            if msg.fabric in self.fabrics:
                name = msg.data["name"]
                if name is not None and len(name) == 0: 
                    name = None
                self.fabrics[msg.fabric].cache.handle_flush(msg.data["cache"], name=name)
            else:
                logger.debug("fabric %s not currently in cache", msg.fabric)
        else:
            logger.warn("invalid flush cache message")

    def set_msg_worker_fabric(self, msg):
        """ create eptWorkerFabric object for this fabric if not already known """
        if msg.fabric not in self.fabrics:
            self.fabrics[msg.fabric] = eptWorkerFabric(msg.fabric)
        setattr(msg, "wf", self.fabrics[msg.fabric])
        setattr(msg, "now", time.time())

    def handle_raw_endpoint_event(self, msg):
        """ receive eptMsgWorkRaw, parse the event, and then execute handle endpoint event """
        classname = msg.data.keys()[0]
        attr = msg.data[classname]
        parsed_msg = msg.wf.ept_epm_parser.parse(classname, attr, attr["_ts"])
        # ensure we copy over msg.now and msg.wf from original msg to parsed_msg
        # (note these are added before handler is called and not in original eptMsgWorker event)
        setattr(parsed_msg, "wf", msg.wf)
        setattr(parsed_msg, "now", msg.now)
        parsed_msg.seq = msg.seq
        logger.debug(parsed_msg)
        self.handle_endpoint_event(parsed_msg)

    def handle_endpoint_event(self, msg):
        """ handle EPM endpoint event """
        logger.debug("%s %.3f: vrf:0x%x, bd:0x%x, pcTag:0x%x, ifId:%s, encap:%s, flags(%s):[%s]",
                msg.status, msg.ts, msg.vrf, msg.bd, msg.pcTag, msg.ifId, msg.encap, len(msg.flags),
                ",".join(msg.flags))

        # use msg fields to get last event for endpoint across all nodes for analysis
        is_rs_ip_event = (msg.wt == WORK_TYPE.EPM_RS_IP_EVENT)
        addr = msg.ip if is_rs_ip_event else msg.addr

        # get cached rapid eptWorkerRapidEndpoint object and ensure not currently is_rapid
        cached_rapid = None
        if msg.wf.settings.analyze_rapid and not msg.force:
            cached_rapid = msg.wf.cache.get_rapid_endpoint(msg.vnid, addr, msg.type)
            if cached_rapid.rapid_count == 0:
                # if entry was not in cache then cached_rapid.type is invalid, let's fix it here
                # (instead on every lookup)
                if is_rs_ip_event or msg.wt == WORK_TYPE.EPM_IP_EVENT:
                    cached_rapid.type = get_addr_type(addr, "ip")
            if self.analyze_rapid(msg, cached_rapid):
                logger.debug("ignoring event, endpoint is_rapid")
                return

        flt = {
            "fabric": msg.fabric,
            "vnid": msg.vnid,
            "addr": addr,
        }
        projection = {
            "node": 1,
            "watch_stale_ts":1,         # will embed value into events.0
            "watch_stale_event":1,      # will embed value into events.0
            "watch_offsubnet_ts": 1,    # will embed value into events.0
            "events": {"$slice": 1}     # pull only events.0
        }
        per_node_history_events = {}    # one entry per node, indexed by node-id
        for h in self.db[eptHistory._classname].find(flt, projection):
            events = []
            for event in h["events"]:
                events.append(eptHistoryEvent.from_dict(event))
            # embed watch info into events.0
            if len(events) > 0:
                events[0].watch_stale_ts = h["watch_stale_ts"]
                events[0].watch_stale_event = eptStaleEvent.from_dict(h["watch_stale_event"])
                events[0].watch_offsubnet_ts = h["watch_offsubnet_ts"]
                per_node_history_events[h["node"]] = events

        # update endpoint history table and determine based on event if analysis is required
        # if this is a new event, the event is inserted into per_node_history_events 
        analysis_required = self.update_endpoint_history(msg, per_node_history_events)

        # we no longer care what the original msg event type. However, we need to maintain the 
        # correct key (fabric, vnid, addr, node) and to ensure that addr is pointing to correct
        # value for EPM_RS_IP_EVENTs. Also, we need to update type to 'ip'.
        if is_rs_ip_event:
            msg.addr = msg.ip
            msg.type = "ip"

        # update ept_endpoint with local event. Return last locals events for move analyze
        # note the result may be None if endpoint is_rapid
        update_local_result = self.update_local(msg, per_node_history_events, cached_rapid) 

        # perform move/offsubnet/stale analysis
        if (analysis_required or msg.force) and update_local_result is not None:
            if msg.wf.settings.analyze_move:
                if update_local_result.analyze_move:
                    self.analyze_move(msg, update_local_result.local_events)
                else:
                    logger.debug("skipping analyze move since update_local produced no update")
            if msg.wf.settings.analyze_offsubnet:
                self.analyze_offsubnet(msg, per_node_history_events, update_local_result)
            if msg.wf.settings.analyze_stale:
                self.analyze_stale(msg, per_node_history_events, update_local_result)

    def update_endpoint_history(self, msg, per_node_history_events):
        """ push event into eptHistory table and determine if analysis is required """
        # already have basic info logged when event was received (fabric, wt, node, vnid, addr, ip)
        # let's add ts, status, flags, ifId, pctag, vrf, bd, encap for full picture
        logger.debug("update endpoint history")

        cache = msg.wf.cache
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
                    # TODO - in the future we can look into mapping vl ip to hostname or perhaps 
                    # tracking tunnel remote to physical interface based on mac entry for tunnel
                    ifId_name = "vl-%s" % tunnel.dst

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
        setattr(msg, "epg_name", cache.get_epg_name(msg.vrf, msg.pcTag) if msg.pcTag>1 else "")
        setattr(msg, "remote", remote)
        setattr(msg, "ifId_name", ifId_name)
        setattr(msg, "tunnel_flags", tunnel_flags)
        # get eptVnid object for vnid. Use it to set the vnid name and if external, override the
        # msg.encap with the bd encap
        ept_vnid = cache.get_vnid_name(msg.vnid, return_object=True)
        if ept_vnid is not None:
            setattr(msg, "vnid_name", ept_vnid.name)
            if ept_vnid.external:
                msg.encap = ept_vnid.encap
        else:
            setattr(msg, "vnid_name", "")

        # eptHistoryEvent representing current received event
        event = eptHistoryEvent.from_msg(msg)

        # prepare filter for push_event
        flt = {
            "fabric": msg.fabric,
            "node": msg.node,
            "vnid": msg.vnid,
            "addr": msg.ip if is_rs_ip_event else msg.addr
        }
        # get last event from eptHistory 
        last_event = per_node_history_events.get(msg.node, None)
        if last_event is None:
            logger.debug("new endpoint on node %s", msg.node)
            if not is_created:
                logger.debug("ignorning deleted/modified event for non-existing eptHistory")
                return False
            # add new entry to db with most recent msg as the only event
            if is_rs_ip_event:
                # if this is new endpoint from rs_ip_event, ensure address is ip and rw info set
                event.rw_mac = msg.addr
                event.rw_bd = msg.bd
                eptHistory(fabric=msg.fabric, node=msg.node, vnid=msg.vnid, addr=msg.ip, 
                        type=msg.type, count=1, events=[event.to_dict()]).save(refresh=False)
            else:
                eptHistory(fabric=msg.fabric, node=msg.node, vnid=msg.vnid, addr=msg.addr, 
                        type=msg.type, count=1, events=[event.to_dict()]).save(refresh=False)
            per_node_history_events[msg.node] = [event]

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
        else:
            # copy down watch_ts from last_event into current event.  This is not used for current
            # function but used by suppression in later analysis
            last_event = last_event[0]
            event.watch_stale_ts = last_event.watch_stale_ts
            event.watch_stale_event = last_event.watch_stale_event
            event.watch_offsubnet_ts = last_event.watch_offsubnet_ts

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
                msg.wf.push_event(eptHistory._classname, flt, event.to_dict())
                per_node_history_events[msg.node].insert(0, event)
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
            event.vnid_name = last_event.vnid_name
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
            msg.wf.push_event(eptHistory._classname, flt, event.to_dict())
            per_node_history_events[msg.node].insert(0, event)
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

    def update_local(self, msg, per_node_history_event, cached_rapid):
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
            "learn_type": 1,
            "is_stale": 1,
            "is_offsubnet": 1,
            "events": {"$slice": 2},
            # rapid thresholds
            "is_rapid": 1,
            "rapid_lts": 1,
            "rapid_count": 1,
            "rapid_lcount": 1,
            "rapid_icount": 1,
        }
        flt = {     
            "fabric": msg.fabric,
            "vnid": msg.vnid,
            "addr": msg.addr,
        }
        endpoint = self.db[eptEndpoint._classname].find_one(flt, projection)
        # if analyze_rapid is enabled and cached_rapid.rapid_count is 0, then no rapid calculation
        # has been performed yet and we need to update all values and trigger analysis. Else,
        # just update rapid_count. note cached_rapid is None if analyze_rapid is disabled
        if not msg.force and cached_rapid is not None and endpoint is not None:
            if cached_rapid.rapid_count == 0:
                cached_rapid.rapid_count = endpoint["rapid_count"] + 1
                cached_rapid.rapid_lts = endpoint["rapid_lts"]
                cached_rapid.rapid_lcount = endpoint["rapid_lcount"]
                cached_rapid.rapid_icount = endpoint["rapid_icount"]
                cached_rapid.is_rapid = endpoint["is_rapid"]
                if self.analyze_rapid(msg, cached_rapid, increment=False):
                    return None
            else:
                # entry actual came from cache, analysis already performed, only need to update count
                cached_rapid.rapid_count+= 1

        # set learn type based on initial node info. This is used on initial event and non-local 
        # events where learn has changed from epg to non-epg.
        learn_type_flags = []
        if msg.node in per_node_history_event:
            learn_type_flags = per_node_history_event[msg.node][0].flags
        learn_type = msg.wf.get_learn_type(msg.vnid, flags=learn_type_flags)

        last_event = None
        last_learn_type = None
        if endpoint is not None:
            ret.is_offsubnet = endpoint["is_offsubnet"]
            ret.is_stale = endpoint["is_stale"]
            if len(endpoint["events"])>0:
                ret.exists = True
                ret.local_events = [eptEndpointEvent.from_dict(e) for e in endpoint["events"]]
                last_event = ret.local_events[0]
            last_learn_type = endpoint["learn_type"]
        else:
            # always create an eptEndpoint object for the endpoint even if no local events are 
            # ever created for it. Without eptEndpoint object then eptHistory total endpoints will
            # be out of sync. This is common scenario for vip/cache/psvi/loopback endpoints that may
            # never have rw info and thus never 'complete local'
            # there is one exception, if endpoint is None and event is a delete, then ignore it
            if msg.status == "deleted" or msg.status == "modified":
                logger.debug("ignorning deleted/modified event for non-existing eptEndpoint")
                return None
            endpoint_type = get_addr_type(msg.addr, msg.type)
            dummy_event = eptEndpointEvent.from_dict({"vnid_name":msg.vnid_name}).to_dict()
            logger.debug("learn type set to %s", learn_type)
            eptEndpoint(fabric=msg.fabric, vnid=msg.vnid, addr=msg.addr,type=endpoint_type,
                    first_learn=dummy_event, learn_type=learn_type).save(refresh=False)

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
            # need to check if learn_type has changed from epg to non-epg, which is only scenario
            # that allows update of learn_type when local_event does not exists.
            if last_learn_type is not None and last_learn_type=="epg" and learn_type!="epg":
                logger.debug("updating learn_type from %s to %s", last_learn_type, learn_type)
                self.db[eptEndpoint._classname].update(flt, 
                    {"$set":{"learn_type": learn_type}}
                )
            if last_event is not None and last_event.node > 0:
                local_event = eptEndpointEvent.from_dict({
                    "ts":msg.ts, 
                    "status":"deleted",
                    # maintain vnid_name and epg_name even on delete
                    "vnid_name": last_event.vnid_name,
                    "epg_name": last_event.epg_name,
                })
                logger.debug("adding delete event to endpoint table: %s", local_event)
                msg.wf.push_event(eptEndpoint._classname,flt,local_event.to_dict(),per_node=False)
                ret.local_events.insert(0, local_event)
            else:
                logger.debug("ignoring local delete event for XR/deleted/non-existing endpoint")
        else:
            # set learn type from local_node
            learn_type_flags = []
            if local_node in per_node_history_event:
                learn_type_flags = per_node_history_event[local_node][0].flags
            learn_type = msg.wf.get_learn_type(msg.vnid, flags=learn_type_flags)

            # flags is in eptHistory event but not eptNode event. Need to maintain flags before 
            # casting eptHistoryEvent local_event to eptEndpointEvent
            local_event_flags = local_event.flags
            local_event = eptEndpointEvent.from_history_event(local_node, local_event)
            # set pod-id for local event (this is before vpc remap so node is actual fabric node)
            local_event.pod = msg.wf.cache.get_pod_id(local_event.node)
            logger.debug("best local set to: %s", local_event)
            # map local_node to vpc value if this is a vpc
            if "vpc-attached" in local_event_flags:
                peer_node = msg.wf.cache.get_peer_node(local_event.node)
                if peer_node == 0:
                    logger.warn("failed to determine peer node for node 0x%04x", local_node)
                    return ret
                local_event.node = get_vpc_domain_id(local_event.node, peer_node)
            # create dict event to write to db
            db_event = local_event.to_dict()
            # if this is the first event, then set first_learn, count, and events in single update
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
                    logger.debug("local_event is less recent than eptEndpoint last_event(%.3f<%.3f)",
                        local_event.ts, last_event.ts)
                    # this should only happen if events are received out of order (perhaps a refresh
                    # from user or resume from rapid while other events are queued or during start
                    # up where new events were received on subscription before build completed).
                    # the last_event must no longer be valid else it would have been choosen as the 
                    # best local_event. therefore, we need to treat this as a delete of last local
                    de = eptEndpointEvent.from_dict({
                        "ts":msg.ts, 
                        "status":"deleted",
                        # maintain vnid_name and epg_name even on delete
                        "vnid_name": last_event.vnid_name,
                        "epg_name": last_event.epg_name,
                    })
                    logger.debug("adding delete event to endpoint table: %s", de)
                    msg.wf.push_event(eptEndpoint._classname,flt,de.to_dict(),per_node=False)
                    ret.local_events.insert(0, de)
                else:
                    for a in ["node", "pctag", "encap", "intf_id", "rw_mac", "rw_bd"]:
                        if getattr(last_event, a) != getattr(local_event, a):
                            logger.debug("%s changed from '%s' to '%s'", a, getattr(last_event,a),
                                    getattr(local_event,a))
                            updated = True
                            # only one update required to trigger updated logic...
                            break
                    # check if learn_type has changed for this complete event
                    if last_learn_type is not None and last_learn_type!=learn_type:
                        logger.debug("learn type updated from %s to %s",last_learn_type,learn_type)
                        self.db[eptEndpoint._classname].update(flt, 
                            {"$set":{"learn_type": learn_type}}
                        )
                    if updated:
                        # if the previous entry was a delete and the current entry is not a delete, 
                        # then check for possible merge.
                        if last_event.node==0 and local_event.node>0 and ts_delta<=TRANSITORY_DELETE:
                            logger.debug("overwritting eptEndpoint [ts delta(%.3f) < %.3f] with: %s",
                                ts_delta, TRANSITORY_DELETE, local_event)
                            self.db[eptEndpoint._classname].update(flt, 
                                    {"$set":{"events.0": db_event}}
                                )
                            ret.local_events[0] = local_event
                            ret.analyze_move = True
                        # push new event to eptEndpoint events  
                        else:
                            logger.debug("adding event to eptEndpoint: %s", local_event)
                            msg.wf.push_event(eptEndpoint._classname, flt, db_event, per_node=False)
                            ret.local_events.insert(0, local_event)
                            ret.analyze_move = True
                    else:
                        logger.debug("no update detected for eptEndpoint")

        if len(ret.local_events)>0:
            logger.debug("final local result: %s", ret.local_events[0])
        else:
            logger.debug("final local result: empty")
        # return last local endpoint events
        return ret

    def analyze_rapid(self, msg, cached_rapid, increment=True):
        """ receive eptMsgWorkEpmEvent and rapidCachedEndpointObject and perform rapid analysis.
            if endpoint has become rapid, then add event to eptRapid table and send to watcher for
            notification and refresh. Update eptEndpoint counters at RAPID_CALCULATE_INTERVAL

            return true if is_rapid
        """
        logger.debug("analyze rapid: %s", cached_rapid)
        if cached_rapid.rapid_count == 0:
            # this is new cached object that has not yet been initialized, always false
            return False
        # should never see counter wrap but just in case...
        if cached_rapid.rapid_count < 0: cached_rapid.rapid_count = 0
        force = False
        ts_delta = msg.now - cached_rapid.rapid_lts
        if cached_rapid.is_rapid:
            # if currently rapid, then only check to see if rapid_holdtime has expired
            if ts_delta > msg.wf.settings.rapid_holdtime:
                logger.debug("clearing is_rapid flag (delta %.3f > %.3f)", ts_delta, 
                                msg.wf.settings.rapid_holdtime)
                cached_rapid.is_rapid = False
                # force recalculate of is_rapid
                force = True
            else:
                # always increment ignored count if is_rapid is set
                cached_rapid.rapid_icount+=1
                if increment:
                    # increment set to false if update_local already updated count, else if pulled
                    # from cache then need to manually increment
                    cached_rapid.rapid_count+=1
                return True

        if ts_delta > RAPID_CALCULATE_INTERVAL or force:
            # calculate new rate and determine if endpoint is_rapid
            # note that threshold is measured as events per minute
            rate = 60.0*(cached_rapid.rapid_count - cached_rapid.rapid_lcount)/ts_delta
            cached_rapid.is_rapid = rate > msg.wf.settings.rapid_threshold
            cached_rapid.rapid_lts = msg.now
            cached_rapid.rapid_lcount = cached_rapid.rapid_count
            if cached_rapid.is_rapid:
                cached_rapid.is_rapid_ts = msg.now
                # add event to eptRapid table 
                # no duplicate check and ensure all values are set so upsert works
                vnid_name = msg.wf.cache.get_vnid_name(cached_rapid.vnid)
                msg.wf.push_event(eptRapid._classname, {
                        "fabric": cached_rapid.fabric,
                        "addr": cached_rapid.addr,
                        "vnid": cached_rapid.vnid,
                        "type": cached_rapid.type,
                    }, {
                        "ts": cached_rapid.rapid_lts,
                        "count": cached_rapid.rapid_count,
                        "rate": rate,
                        "vnid_name": vnid_name,
                    })
                # send msg for WATCH_Rapid
                mmsg = eptMsgWorkWatchRapid(cached_rapid.addr,"watcher",{
                        "vnid": cached_rapid.vnid,
                        "type": cached_rapid.type,
                        "ts": cached_rapid.rapid_lts,
                        "count": cached_rapid.rapid_count,
                        "rate": rate,
                    },WORK_TYPE.WATCH_RAPID, fabric=msg.fabric)
                logger.debug("sending rapid event to watcher")
                self.send_msg(mmsg)

            logger.debug("rapid rate:%.3f, ts:%.3f, rapid:%r",rate,ts_delta,cached_rapid.is_rapid)
            cached_rapid.save() 
        return cached_rapid.is_rapid

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
            logger.debug("new move detected")
            endpoint_type = get_addr_type(msg.addr, msg.type)
            eptMove(fabric=msg.fabric, vnid=msg.vnid, addr=msg.addr, type=endpoint_type,
                    count=1, events=[move_event]).save(refresh=False)
        else:
            db_src = eptMoveEvent.from_dict(db_move["events"][0]["src"])
            db_dst = eptMoveEvent.from_dict(db_move["events"][0]["dst"])
            logger.debug("checking if move event is different from last eptMove event")
            move_uniq=eptMoveEvent.is_different(db_src,src) or eptMoveEvent.is_different(db_dst,dst)
            if not move_uniq:
                logger.debug("move is duplicate of previous move event")
                return
            logger.debug("new move detected")
            msg.wf.push_event(eptMove._classname, flt, move_event)

        if msg.wf.notification_enabled("move")["enabled"]:
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
                if event.pctag > 1 and event.status != "deleted":
                    # skip offsubnet analysis based on endpoint flags
                    if "loopback" in event.flags or \
                        "vtep" in event.flags or \
                        "svi" in event.flags or \
                        "psvi" in event.flags or \
                        "cached" in event.flags or \
                        "static" in event.flags:
                        logger.debug("skipping offsubnet analysis on node 0x%04x with flags: [%s]", 
                                node, ",".join(event.flags))
                        continue
                    #logger.debug("checking if [node:0x%04x 0x%06x, 0x%x, %s] is offsubnet", 
                    #    node, msg.vnid, event.pctag, msg.addr)
                    if msg.wf.cache.ip_is_offsubnet(msg.vnid,event.pctag,msg.addr):
                        offsubnet_nodes[node] = eptOffSubnetEvent.from_history_event(event)
        # update eptHistory is_offsubnet flags
        logger.debug("offsubnet on total of %s nodes", len(offsubnet_nodes))
        flt = {
            "fabric": msg.fabric,
            "vnid": msg.vnid,
            "addr": msg.addr,
        }
        self.db[eptHistory._classname].update_many(flt, {"$set":{"is_offsubnet":False}})
        if len(offsubnet_nodes)>0:
            nlist = []
            for node in offsubnet_nodes:
                logger.debug("setting is_offsubnet to True for node 0x%04x", node)
                nlist.append({"node":node})
                # update the event timestamp to msg.ts as node is detected as offsubnet based on this
                # recent event.
                offsubnet_nodes[node].ts = msg.ts
            flt["$or"] = nlist
            self.db[eptHistory._classname].update_many(flt, {"$set":{"is_offsubnet":True}})
        # clear eptEndpoint is_offsubnet flag if not currently offsubnet on any node
        elif update_local_result.is_offsubnet:
            logger.debug("clearing eptEndpoint is_offsubnet flag")
            self.db[eptEndpoint._classname].update_one(flt, {"$set":{"is_offsubnet":False}})

        # suppress the event to watcher if within suppress interval
        if len(offsubnet_nodes)>0:
            suppress_nodes = []
            # need to suppress rapid events if recent watch job created
            # last watch_offsubnet_ts is embedded/hacked in per_node_history_events
            for node in offsubnet_nodes:
                if node in per_node_history_events:
                    delta = msg.ts - per_node_history_events[node][0].watch_offsubnet_ts
                    if delta != 0 and delta < SUPPRESS_WATCH_OFFSUBNET:
                        logger.debug("suppress watch_offsubnet for node 0x%04x (delta %.03f<%.03f)", 
                                node, delta, SUPPRESS_WATCH_OFFSUBNET)
                        suppress_nodes.append(node)

            # remove suppress_nodes from offsubnet_nodes list
            for node in suppress_nodes:
                offsubnet_nodes.pop(node, None)
            # create work for WATCH_OFFSUBNET for each non-suppressed offsubnet events and set 
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

        logger.debug("analyze stale")
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

        stale_nodes = {}    # indexed by node with eptStaleEvent
        for node in per_node_history_events:
            h_event = per_node_history_events[node][0]
            event = eptStaleEvent.from_history_event(local_node, h_event)
            # only perform analysis on non-deleted entries
            if h_event.status != "deleted":
                # TODO - add check for interface that proxy-acast-X if bounce-to-proxy is set
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
                            if msg.wf.settings.stale_multiple_local:
                                stale_nodes[node] = event
                            else:
                                logger.debug("igorning stale_multiple_local")
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
                                # if XR node is 0 then there was a tunnel mapping error. 
                                # Theoretically this could be an invalid/no longer existing tunnel
                                # but it's more likely that the app/worker is behind or out of sync
                                # with recent tunnel updates. This could also be transient issue for
                                # vpc peer where local flag has not been set.
                                if h_event.remote == 0:
                                    logger.debug("skipping stale on %s with unresolved XR node %s", 
                                            node, h_event.remote)
                                else:
                                    logger.debug("stale on %s to %s", node, h_event.remote)
                                    stale_nodes[node] = event
                else:
                    # non-deleted event when endpoint is not currently learned within the fabric
                    if msg.wf.settings.stale_no_local:
                        # if there is no local set and this node has 'local' flag, then it must be
                        # a transient event and we're waiting on rewrite info OR it is an old event
                        # where we are waiting for the delete. we will consider this a type of 
                        # stale_multiple_local
                        if "local" in h_event.flags:
                            logger.debug("node %s claiming local with incomplete local_node", node)
                            if msg.wf.settings.stale_multiple_local:
                                logger.debug("stale on %s to %s (no local)", node, h_event.remote)
                                stale_nodes[node] = event
                        else:
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
        if len(stale_nodes)>0:
            nlist = []
            for node in stale_nodes:
                logger.debug("setting is_stale to True for node 0x%04x", node)
                # update the event timestamp to msg.ts as node is detected as stale based on this
                # recent event.
                stale_nodes[node].ts = msg.ts
                nlist.append({"node":node})
            flt["$or"] = nlist
            self.db[eptHistory._classname].update_many(flt, {"$set":{"is_stale":True}})
        # clear eptEndpoint is_stale flag if not currently stale on any node
        elif update_local_result.is_stale:
            logger.debug("clearing eptEndpoint is_stale flag")
            flt.pop("node",None)
            self.db[eptEndpoint._classname].update_one(flt, {"$set":{"is_stale":False}})

        # suppress the event to watcher if within suppress interval
        if len(stale_nodes)>0:
            suppress_nodes = []

            # need to suppress rapid events if recent watch job created
            # last watch_stale_ts and watch_stale_event is embedded/hacked in per_node_history_events
            for node in stale_nodes:
                if node in per_node_history_events:
                    last_node_event = per_node_history_events[node][0]
                    delta = msg.ts - last_node_event.watch_stale_ts
                    if delta != 0 and delta < SUPPRESS_WATCH_STALE:
                        # if this stale event is non-duplicate of previous event, then we need to 
                        # skip suppression and send updated stale event to watcher.
                        stale_event = stale_nodes[node]
                        if stale_event.is_duplicate(last_node_event.watch_stale_event):
                            logger.debug("suppress watch_stale for node 0x%04x (delta %.03f<%.03f)", 
                                node, delta, SUPPRESS_WATCH_STALE)
                            suppress_nodes.append(node)

            # remove suppress_nodes from offsubnet_nodes list
            for node in suppress_nodes:
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
                        "watch_stale_ts": msg.ts,
                        "watch_stale_event": stale_nodes[node].to_dict()
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
        parser = msg.wf.ept_epm_parser
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
        msg.wf.send_notification("move", subject, txt)

    def handle_watch_rapid(self, msg):
        """ receive an eptMsgWorkRapid message and immediately performs notification action. If
            refresh_rapid is enabled, then adds the object to watch_rapid dict with execute
            timestamp (xts) of msg.ts + eptSettings.rapid_holdtime + TRANSITORY_RAPID timer. If 
            object already exists it is overwritten with new watch event. This allows suppression
            of refresh events for endpoints that are continuously 'rapid' and waits until they 
            stable before performing api refresh
        """
        # build notification msg and execute notify send
        subject = "rapid endpoint %s" % msg.addr
        txt = "rapid endpoint detected [fabric: %s, %s, addr: %s] rate %.3f" % (
            msg.fabric,
            msg.vnid_name if len(msg.vnid_name)>0 else "vnid:%d" % msg.vnid,
            msg.addr,
            msg.rate
        )
        msg.wf.send_notification("rapid", subject, txt)
        if msg.wf.settings.refresh_rapid:
            key = "%s,%s,%s" % (msg.fabric, msg.vnid, msg.addr)
            msg.xts = msg.now + msg.wf.settings.rapid_holdtime + TRANSITORY_RAPID
            with self.watch_rapid_lock:
                self.watch_rapid[key] = msg
            logger.debug("watch rapid added with xts: %.03f, delta: %.03f", msg.xts, msg.xts-msg.now)

    def handle_watch_offsubnet(self, msg):
        """ recieves an eptMsgWorkWatchOffSubnet message and adds object to watch_offsubnet dict with 
            execute timestamp (xts) of msg.ts + TRANSITORY_OFFSUBNET timer. If object already
            exists it is overwritten with the new watch event.
        """
        key = "%s,%s,%s,%s" % (msg.fabric, msg.vnid, msg.addr, msg.node)
        msg.xts = msg.now + TRANSITORY_OFFSUBNET
        with self.watch_offsubnet_lock:
            self.watch_offsubnet[key] = msg
        logger.debug("watch offsubnet added with xts: %.03f, delta: %.03f", msg.xts, msg.xts-msg.now)

    def handle_watch_stale(self, msg):
        """ recevie an eptMsgWorkWatchStale message and adds object to watch_stale dict with execute
            timestamp (xts) of msg.ts + TRANSITORY_STALE or TRANSITORY_STALE_NO_LOCAL timer.
            If object already exists it is overwritten with the new watch event.
        """
        key = "%s,%s,%s,%s" % (msg.fabric, msg.vnid, msg.addr, msg.node)
        if msg.event["expected_remote"] == 0:
            msg.xts = msg.now + TRANSITORY_STALE_NO_LOCAL
        else:
            msg.xts = msg.now + TRANSITORY_STALE
        with self.watch_stale_lock:
            self.watch_stale[key] = msg
        logger.debug("watch stale added with xts: %.03f, delta: %.03f", msg.xts, msg.xts-msg.now)

    def execute_watch(self):
        """ check for watch events with execute ts ready and perform corresponding actions
            reset timer to perform event again at next WATCH_INTERVAL
        """
        self.execute_generic_watch("offsubnet")
        self.execute_generic_watch("stale")
        self.execute_watch_rapid()

    def watcher_get_xts_ready(self, lock, msgs):
        """ receive a lock and dict 'msgs' and pop off msgs that are ready to execute.
            return tuple (key, msg) of ready msgs
        """
        ts = time.time()
        work = []               # tuple of (key, msg) of watch event that is ready
        paused = {}             # count of work per fabric for accounting only
        with lock:
            # get msg events that are ready, remove key from corresponding dict
            for k, msg in msgs.items():
                if msg.wf.watcher_paused:
                    if msg.fabric not in paused:
                        paused[msg.fabric] = 0
                    paused[msg.fabric]+=1
                else:
                    if msg.xts <= ts: 
                        work.append((k, msg))
            for (k, msg) in work: msgs.pop(k, None)
        if len(paused) > 0:
            for fab in paused:
                logger.debug("paused %s watch events for fabric %s", paused[fab], fab)
        return work

    def execute_watch_rapid(self):
        """ get list of rapid msgs that are ready to execute and if is_rapid has cleared OR endpoint
            has is_rapid still set but current rapid calculation implies endpoint is no longer rapid,
            then perform refresh
        """
        work = self.watcher_get_xts_ready(self.watch_rapid_lock, self.watch_rapid)
        if len(work) > 0:
            logger.debug("execute %s ready watch rapid events", len(work))
            for (k, msg) in work:
                logger.debug("checking: %s", msg)
                flt = {
                    "fabric": msg.fabric,
                    "addr": msg.addr,
                    "vnid": msg.vnid,
                }
                projection = {"events":{"$slice":1}}
                endpoint = self.db[eptEndpoint._classname].find_one(flt, projection)
                if endpoint is not None:
                    is_rapid = endpoint["is_rapid"]
                    if is_rapid:
                        ts_delta = time.time() - endpoint["rapid_lts"]
                        rate = 0
                        if ts_delta > 0:
                            rate = 60.0*(endpoint["rapid_count"]-endpoint["rapid_lcount"])/ts_delta
                            is_rapid = rate > msg.wf.settings.rapid_threshold
                        logger.debug("updating is_rapid to %r from current rate %.3f",is_rapid,rate)
                    if not is_rapid: 
                        logger.debug("is_rapid is False, requesting refresh")
                        msg = eptMsgSubOp(MSG_TYPE.REFRESH_EPT, data ={
                            "fabric": msg.fabric,
                            "addr": msg.addr,
                            "vnid": msg.vnid,
                            "type": msg.type,
                        })
                        self.redis.publish(SUBSCRIBER_CTRL_CHANNEL, msg.jsonify())
                        self.increment_stats(SUBSCRIBER_CTRL_CHANNEL, tx=True)
                    else:
                        logger.debug("is_rapid is True, skipping refresh")
                else:
                    logger.debug("endpoint not found in db")

    def execute_generic_watch(self, watch_type):
        """ loop through all events in watch_type dict. for each event with xts ready check if 
            watch_type (is_offsubnet/is_stale) value within corresponding eptHistory object is set.
            If true, update eptEndpoint (is_offsubnet/is_stale) attribute and then perform 
            configured notify and remediate actions.  Add object ept collection with dup check, 
            but perform remediation action unconditionally.
        """
        if watch_type == "offsubnet":
            lock = self.watch_offsubnet_lock
            msgs = self.watch_offsubnet
            ept_db = eptOffSubnet
            ept_db_attr = "is_offsubnet"
            event_class = eptOffSubnetEvent
            remediate_attr = "auto_clear_offsubnet"
            work = self.watcher_get_xts_ready(lock, msgs)
        elif watch_type == "stale":
            lock = self.watch_stale_lock
            msgs = self.watch_stale
            ept_db = eptStale
            ept_db_attr = "is_stale"
            event_class = eptStaleEvent
            remediate_attr = "auto_clear_stale"
            work = self.watcher_get_xts_ready(lock, msgs)
        else:
            logger.error("unsupported watch type '%s'", watch_type)
            return

        if len(work) > 0:
            clear_events = []   # list of clear tuples (cmd, key, reason, event)
            logger.debug("execute %s ready watch %s events", len(work), watch_type)
            for (key, msg) in work:
                logger.debug("checking: %s", msg)
                # check if key is in watch_rapid, if so ignore this event
                rapid_key = "%s,%s,%s" % (msg.fabric, msg.vnid, msg.addr)
                if rapid_key in self.watch_rapid:
                    logger.debug("skipping execute event as endpoint is flagged as rapid")
                    continue
                flt = {
                    "fabric": msg.fabric,
                    "vnid": msg.vnid,
                    "addr": msg.addr,
                    "node": msg.node,
                }
                projection = {
                    ept_db_attr: 1,
                    "events": {"$slice": 4},
                }
                h = self.db[eptHistory._classname].find_one(flt, projection)
                if h is None or not h[ept_db_attr]:
                    logger.debug("%s is false", ept_db_attr)
                else:
                    logger.debug("%s is true, updating eptEndpoint", ept_db_attr)
                    # update eptEndpoint object 
                    flt2 = copy.copy(flt)
                    flt2.pop("node",None)
                    self.db[eptEndpoint._classname].update_one(flt2, {"$set":{ept_db_attr:True}})
                    
                    # for db push, the only non-key value not present is 'type' which we will set as
                    # a key to allow proper upsert functionality if object does not exists (upsert)
                    key = copy.copy(flt)
                    key["type"] = msg.type
                    event = event_class.from_dict(msg.event)

                    # dup check is two parts. dup flag is initialized to false and set to true if
                    # last event is_duplicate of current event. dup flag can then be cleared if 
                    # a delete has occurred in eptHistory since the last event_class event. either 
                    # ways we need to do a read of event_class.  this is useful because watch events
                    # that are still offsubnet/stale are less frequently than analyze_stale or 
                    # anaylze_offsubnet events. The hope is reads in the watch reduce reads in the 
                    # worker nodes
                    is_duplicate = False
                    db_obj = self.db[ept_db._classname].find_one(flt,{"events":{"$slice":1}})
                    if db_obj is not None and "events" in db_obj and len(db_obj["events"])>0:
                        db_event = event_class.from_dict(db_obj["events"][0])
                        if event.is_duplicate(db_event):
                            is_duplicate = True
                            # check if there was a delete since db_event
                            for h_event in h["events"]:
                                if h_event["ts"] > db_event.ts and h_event["status"] == "deleted":
                                    is_duplicate = False
                                    break
                    if is_duplicate:
                        logger.debug("suppressing notification and db update for duplicate event")
                    else:
                        msg.wf.push_event(ept_db._classname, key, event.to_dict())
                        # send notification if enabled
                        subject = "%s event for %s" % (watch_type, msg.addr)
                        txt = "%s event [fabric: %s, %s, addr: %s] %s" % (
                            watch_type,
                            msg.fabric,
                            event.vnid_name if len(event.vnid_name)>0 else "vnid:%d" % msg.vnid,
                            msg.addr,
                            event.notify_string()
                        )
                        msg.wf.send_notification(watch_type, subject, txt)

                    # even if duplicate, add to clear list if remediation is enabled
                    if getattr(msg.wf.settings, remediate_attr):
                        logger.debug("%s enabled, adding endpoint to clear list", remediate_attr)
                        cmd = "clear --fabric %s --pod %s --node %s --addr %s --vnid %s " % (
                                msg.fabric,
                                msg.wf.cache.get_pod_id(msg.node),
                                msg.node,
                                msg.addr,
                                msg.vnid)
                        if msg.type == "mac":
                            cmd+= "--addr_type mac"
                        else:
                            cmd+= "--addr_type ip --vrf_name \"%s\""%parse_vrf_name(event.vnid_name)
                        clear_events.append((cmd,key,ept_db_attr,event)) 
            # perform clear action for all clear cmds
            if len(clear_events) > 0:
                logger.debug("executing %s clear endpoint commands", len(clear_events))
                ts = time.time()
                for (cmd, key, ept_db_attr, event) in clear_events:
                    if execute_worker(cmd):
                        # add event to eptRemediate and send notification if enabled
                        reason = "stale" if ept_db_attr == "is_stale" else "offsubnet"
                        msg.wf.push_event(eptRemediate._classname, key, {
                            "ts": ts,
                            "vnid_name": event.vnid_name,
                            "action": "clear",
                            "reason": reason,
                        })
                        # send notification if enabled
                        subject = "auto-clear %s endpoint" % reason
                        txt = "auto-clear %s endpoint [fabric: %s, %s, addr: %s]" % (
                            reason,
                            key["fabric"],
                            event.vnid_name if len(event.vnid_name)>0 else "vnid:%d" % key["vnid"],
                            key["addr"],
                        )
                        msg.wf.send_notification("clear", subject, txt)

    def handle_endpoint_delete(self, msg):
        """ handle endpoint delete requests.  This needs to flush the local cache and delete all
            eptEndpoint object using rest object (which will trigger delete of all appropriate 
            dependencies)
            caches:
                rapid_cache
        """
        logger.debug("deleting %s [0x%06x %s]", msg.fabric, msg.vnid, msg.addr)
        # remove from local caches
        cache = msg.wf.cache
        key = cache.get_key_str(addr=msg.addr, vnid=msg.vnid)
        cache.rapid_cache.remove(key)
        # delete from db
        endpoint = eptEndpoint.load(fabric=msg.fabric, vnid=msg.vnid, addr=msg.addr)
        if endpoint.exists():
            endpoint.remove()
        else:
            logger.debug("endpoint not found in db, no delete occurring")

    def handle_test_email(self, msg):
        """ receive eptMsgWork with WORK_TYPE.TEST_EMAIL and send a test email """
        logger.debug("sending test email")
        txt = "%s test email" % msg.fabric
        msg.wf.send_notification("any_email", txt, txt)

    def handle_test_syslog(self, msg):
        """ receive eptMsgWork with WORK_TYPE.TEST_SYSLOG and send a test syslog """
        logger.debug("sending test syslog")
        txt = "%s test syslog" % msg.fabric
        msg.wf.send_notification("any_syslog", txt, txt)

    def handle_settings_reload(self, msg):
        """ receive eptMsgWork with WORK_TYPE.SETTINGS_RELOAD to reload local wf settings """
        logger.debug("reloading settings for fabric %s", msg.fabric)
        msg.wf.settings_reload()

    def handle_epm_eof(self, msg):
        """ receive eptMsgWork with WORK_TYPE.FABRIC_EPM_EOF and send ack back to subscriber """
        logger.debug("received epm eof for fabric %s", msg.fabric)
        self.redis.publish(SUBSCRIBER_CTRL_CHANNEL, 
            eptMsgSubOp(MSG_TYPE.FABRIC_EPM_EOF_ACK,data={
                "fabric": msg.fabric,
                "addr": self.worker_id,
                }
            ).jsonify()
        )
        self.increment_stats(SUBSCRIBER_CTRL_CHANNEL, tx=True)

    def handle_watch_pause(self, msg):
        """ receive eptMsgWork with WORK_TYPE.FABRIC_WATCH_PAUSE and set local watcher_pause flag """
        logger.debug("receiving watch pause for fabric %s", msg.fabric)
        msg.wf.watcher_paused = True

    def handle_watch_resume(self, msg):
        """ receive eptMsgWork with WORK_TYPE.FABRIC_WATCH_RESUME and set local watcher_pause flag """
        logger.debug("receiving watch resume for fabric %s", msg.fabric)
        msg.wf.watcher_paused = False

    def handle_std_mo_event(self, msg):
        """ receive eptMsgWork with WORK_TYPE.STD_MO and """
        classname = msg.data.keys()[0]
        attr = msg.data[classname]
        if classname in dependency_map:
            logger.debug("triggering sync_event for dependency %s", classname)
            updates = dependency_map[classname].sync_event(msg.wf.fabric, attr, msg.wf.session)
            logger.debug("updated objects: %s", len(updates))
            # send flush for each update
            for u in updates:
                self.send_flush(u, u.name if hasattr(u, "name") else None)
        else:
            logger.warn("%s not defined in dependency_map", classname)


class eptWorkerUpdateLocalResult(object):
    """ return object for eptWorker.update_loal method """
    def __init__(self):
        self.analyze_move = False       # an update requiring move analysis occurred
        self.local_events = []          # recent (0-3) local eptEndpointEvent objects
        self.is_offsubnet = False       # eptEndpoint object is currently offsubnet
        self.is_stale = False           # eptEndpoint object is currently stale
        self.exists = False             # eptEndpoint entry exists

