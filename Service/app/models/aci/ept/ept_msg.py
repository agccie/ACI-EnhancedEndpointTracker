
from enum import Enum
from enum import unique as enum_unique

import json
import logging
import re
import time

# module level logging
logger = logging.getLogger(__name__)

# static msg types to prevent duplicates
@enum_unique
class MSG_TYPE(Enum):
    WORK                = "work"            # worker from subscriber to manager to worker (or requeued)
    HELLO               = "hello"           # hello from worker to manager
    MANAGER_STATUS      = "manager_status"  # manager status response
    GET_MANAGER_STATUS  = "get_manager_status" # request to get manager status from API to manager
    FABRIC_START        = "fabric_start"    # request from API to manager to start fabric monitor
    FABRIC_STOP         = "fabric_stop"     # request from API to manager to stop fabric monitor
    FABRIC_RESTART      = "fabric_restart"  # request from API or subscriber to manager for restart
    FLUSH_FABRIC        = "flush_fabric"    # request from manager to workers to flush fabric from 
                                            # their local caches

# static work types sent with MSG_TYPE.WORK
@enum_unique
class WORK_TYPE(Enum):
    WATCH_NODE          = "watch_node"      # a new node has become active/inactive
    WATCH_MOVE          = "watch_move"      # an endpoint move event requires watch or notify
    WATCH_STALE         = "watch_stale"     # a stale endpoint event requires watch or notify
    WATCH_OFFSUBNET     = "watch_offsubnet" # an offsubnet endpoint event requires watch or notify
    FLUSH_CACHE         = "flush_cache"     # flush cache for specific collection and/or dn
    EPM_IP_EVENT        = "epm_ip "         # epmIpEp event
    EPM_MAC_EVENT       = "epm_mac"         # epmMacEp event
    EPM_RS_IP_EVENT     = "epmRsIp"         # epmRsMacEpToIpEpAtt event

class eptMsg(object):
    """ generic ept job for messaging between workers 
        NOTE, msg_type must be instance of MSG_TYPE Enum
    """
    def __init__(self, msg_type, data={}, seq=1):
        self.msg_type = msg_type
        self.data = data
        self.seq = seq

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "msg_type": self.msg_type.value,
            "data": self.data,
            "seq": self.seq,
        })

    def __repr__(self):
        return "%s.0x%08x" % (self.msg_type.value, self.seq)

    @staticmethod
    def parse(data):
        # parse data received on message queue and return corresponding EPMsg
        # allow exception to raise on invalid data
        js = json.loads(data)
        if js["msg_type"] == MSG_TYPE.WORK.value:
            return eptMsgWork.from_msg_json(js)
        elif js["msg_type"] == MSG_TYPE.HELLO.value:
            return eptMsgHello.from_msg_json(js)
        return eptMsg(
                    MSG_TYPE(js["msg_type"]), 
                    data=js.get("data", {}),
                    seq = js.get("seq", None)
                )

class eptMsgHello(object):
    """ hello message sent from worker to manager """

    def __init__(self, worker_id, role, queues, start_time, seq=1):
        self.msg_type = MSG_TYPE.HELLO
        self.worker_id = worker_id
        self.role = role
        self.queues = queues            # list of queue names sorted by priority        
        self.start_time = start_time
        self.seq = seq

    def __repr__(self):
        return "[%s] %s.0x%08x" % (self.worker_id, self.msg_type.value, self.seq)

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "msg_type": self.msg_type.value,
            "seq": self.seq,
            "data": {
                "worker_id": self.worker_id,
                "role": self.role,
                "queues": self.queues, 
                "start_time": self.start_time,
            },
        })

    @staticmethod
    def from_msg_json(js):
        # return eptMsgHello object from received msg js
        hello_data = js["data"]
        return eptMsgHello(
            hello_data["worker_id"],
            hello_data["role"],
            hello_data["queues"],
            hello_data["start_time"],
            seq = js["seq"],
        )

class eptMsgWork(object):
    """ primary work message sent from subscriber to manager and then dispatched to a worker  
        Addr is a string that will be used as a simple hash for worker calculation
        qnum is the index for worker queue. At present, all workers should subscribe to 2 queues 
        with strict priority queuing on lowest queue index.
    """

    def __init__(self, addr, role, data, wt, qnum=1, seq=1, fabric=1):
        self.msg_type = MSG_TYPE.WORK
        self.addr = addr
        self.role = role
        self.qnum = qnum
        self.data = data
        self.wt = wt            # WORK_TYPE enum
        self.seq = seq
        self.fabric = fabric

    def __repr__(self):
        return "%s.0x%08x %s %s" % (self.msg_type.value, self.seq, self.role, self.wt.value)

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "msg_type": self.msg_type.value,
            "seq": self.seq,
            "data": self.data,
            "wt": self.wt.value,
            "addr": self.addr,
            "role": self.role,
            "qnum": self.qnum,
            "fabric": self.fabric,
        })

    @staticmethod
    def from_msg_json(js):
        # return eptMsgWork object from received msg js
        # check if this is eptMsgWorkEpmEvent and initialize accordingly
        wt = WORK_TYPE(js["wt"])
        if wt==WORK_TYPE.EPM_IP_EVENT or wt==WORK_TYPE.EPM_MAC_EVENT or wt==WORK_TYPE.EPM_RS_IP_EVENT:
            return eptMsgWorkEpmEvent(js["addr"], js["role"], js["data"], wt,
                        qnum = js["qnum"], seq = js["seq"], fabric= js["fabric"])
        elif wt == WORK_TYPE.WATCH_MOVE:
            return eptMsgWorkWatchMove(js["addr"], js["role"], js["data"], wt,
                        qnum = js["qnum"], seq = js["seq"], fabric= js["fabric"])
        elif wt == WORK_TYPE.WATCH_OFFSUBNET:
            return eptMsgWorkWatchOffSubnet(js["addr"], js["role"], js["data"], wt,
                        qnum = js["qnum"], seq = js["seq"], fabric= js["fabric"])
        elif wt == WORK_TYPE.WATCH_STALE:
            return eptMsgWorkWatchStale(js["addr"], js["role"], js["data"], wt,
                        qnum = js["qnum"], seq = js["seq"], fabric= js["fabric"])
        elif wt == WORK_TYPE.WATCH_NODE:
            return eptMsgWorkWatchNode(js["addr"], js["role"], js["data"], wt,
                        qnum = js["qnum"], seq = js["seq"], fabric= js["fabric"])
        else:
            return eptMsgWork(js["addr"], js["role"], js["data"], wt,
                        qnum = js["qnum"], seq = js["seq"], fabric= js["fabric"])

class eptMsgWorkWatchNode(eptMsgWork):
    """ fixed message type for WATCH_NODE """
    def __init__(self, addr, role, data, wt, qnum=1, seq=1, fabric=1):
        # initialize as eptMsgWork with empty data set
        super(eptMsgWorkWatchNode, self).__init__(addr, "watcher", data, wt, 
                qnum=qnum, seq=seq, fabric=fabric)
        self.wt = WORK_TYPE.WATCH_NODE
        self.ts = float(data.get("ts", 0))
        self.node = int(data.get("node", 0))
        self.status = data.get("status", "")

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "msg_type": self.msg_type.value,
            "seq": self.seq,
            "wt": self.wt.value,
            "addr": self.addr,
            "role": self.role,
            "qnum": self.qnum,
            "fabric": self.fabric,
            "data": {
                "ts": self.ts,
                "node": self.node,
                "status": self.status,
            }
        })
        return ret

    def __repr__(self):
        return "%s.0x%08x %s %s [ts:%.03f node:0x%04x, %s]" % (self.msg_type.value, self.seq, 
                self.fabric, self.wt.value, self.ts, self.node, self.status)

class eptMsgWorkWatchMove(eptMsgWork):
    """ fixed message type for WATCH_MOVE """
    def __init__(self, addr, role, data, wt, qnum=1, seq=1, fabric=1):
        # initialize as eptMsgWork with empty data set
        super(eptMsgWorkWatchMove, self).__init__(addr, "watcher", data, wt, 
                qnum=qnum, seq=seq, fabric=fabric)
        self.wt = WORK_TYPE.WATCH_MOVE
        self.vnid = int(data.get("vnid", 0))
        self.type = data.get("type", "")
        self.src = data.get("src", {})
        self.dst = data.get("dst", {})

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "msg_type": self.msg_type.value,
            "seq": self.seq,
            "wt": self.wt.value,
            "addr": self.addr,
            "role": self.role,
            "qnum": self.qnum,
            "fabric": self.fabric,
            "data": {
                "vnid": self.vnid,
                "type": self.type,
                "src": self.src,
                "dst": self.dst
            }
        })
        return ret

    def __repr__(self):
        return "%s.0x%08x %s %s [0x%06x, %s, %s]" % (self.msg_type.value, 
            self.seq, self.fabric, self.wt.value, self.vnid, self.type, self.addr)


class eptMsgWorkWatchOffSubnet(eptMsgWork):
    """ fixed message type for WATCH_OFFSUBNET """
    def __init__(self, addr, role, data, wt, qnum=1, seq=1, fabric=1):
        # initialize as eptMsgWork with empty data set
        super(eptMsgWorkWatchOffSubnet, self).__init__(addr, "watcher", data, wt, 
                qnum=qnum, seq=seq, fabric=fabric)
        self.wt = WORK_TYPE.WATCH_OFFSUBNET
        self.xts = float(data.get("xts", 0))        # watcher execute timestamp
        self.ts = float(data.get("ts", 0))
        self.vnid = int(data.get("vnid", 0))
        self.node = int(data.get("node", 0))
        self.event = data.get("event", {})

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "msg_type": self.msg_type.value,
            "seq": self.seq,
            "wt": self.wt.value,
            "addr": self.addr,
            "role": self.role,
            "qnum": self.qnum,
            "fabric": self.fabric,
            "data": {
                "ts": self.ts,
                "node": self.node,
                "vnid": self.vnid,
                "event": self.event,
            }
        })
        return ret

    def __repr__(self):
        return "%s.0x%08x %s %s [ts:%.03f node: 0x%04x, 0x%06x, %s]" % (self.msg_type.value, 
            self.seq, self.fabric, self.wt.value, self.ts, self.node, self.vnid, self.addr)

class eptMsgWorkWatchStale(eptMsgWork):
    """ fixed message type for WATCH_STALE """
    def __init__(self, addr, role, data, wt, qnum=1, seq=1, fabric=1):
        # initialize as eptMsgWork with empty data set
        super(eptMsgWorkWatchStale, self).__init__(addr, "watcher", data, wt, 
                qnum=qnum, seq=seq, fabric=fabric)
        self.wt = WORK_TYPE.WATCH_STALE
        self.xts = float(data.get("xts", 0))        # watcher execute timestamp
        self.ts = float(data.get("ts", 0))
        self.vnid = int(data.get("vnid", 0))
        self.node = int(data.get("node", 0))
        self.event = data.get("event", {})

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "msg_type": self.msg_type.value,
            "seq": self.seq,
            "wt": self.wt.value,
            "addr": self.addr,
            "role": self.role,
            "qnum": self.qnum,
            "fabric": self.fabric,
            "data": {
                "ts": self.ts,
                "node": self.node,
                "vnid": self.vnid,
                "event": self.event,
            }
        })
        return ret

    def __repr__(self):
        return "%s.0x%08x %s %s [ts:%.03f node: 0x%04x, 0x%06x, %s]" % (self.msg_type.value, 
            self.seq, self.fabric, self.wt.value, self.ts, self.node, self.vnid, self.addr)

###############################################################################
#
# epm event is a type of eptMsgWork triggered from an epmMacEp, epmIpEp, or
# epmRsMacEpToIpEpAtt event. The heart of this app is parsing and delivering 
# epmEvents.
# Remember - status can be 'created', 'deleted', or 'modified'
#
###############################################################################

# pre-compile regex expressions
epm_reg = "node-(?P<node>[0-9]+)/sys/"
epm_reg+= "((ctx-\[vxlan-(?P<vrf>[0-9]+)\]/)|(?P<ovl>inst-overlay-1/))"
epm_reg+= "(bd-\[vxlan-(?P<bd>[0-9]+)\]/)?"
epm_reg+= "(vx?lan-\[(?P<encap>vx?lan-[0-9]+)\]/)?"
epm_reg+= "db-ep/"
epm_reg+= "((mac|ip)-\[?(?P<addr>[0-9\.a-fA-F:]+)\]?)?"
epm_rsMacToIp_reg = epm_reg+"/rsmacEpToIpEpAtt-.+?"
epm_rsMacToIp_reg+= "ip-\[(?P<ip>[0-9\.a-fA-F\:]+)\]"
epm_rsMacToIp_reg = re.compile(epm_rsMacToIp_reg)
epm_reg = re.compile(epm_reg)

class eptEpmEventParser(object):
    """ shim for creating/parsing epmEvents """
    def __init__(self, fabric, overlay_vnid):
        logger.debug("init parser for fab %s with overlay-vnid: %s", fabric, overlay_vnid)
        self.fabric = fabric
        self.overlay_vnid = int(overlay_vnid)

    def parse(self, classname, attr, ts):
        # return an instance of eptMsgWorkEpmEvent or None on error
        msg = eptMsgWorkEpmEvent(None, "worker", {}, None, fabric=self.fabric)
        if not msg.parse(self.overlay_vnid, classname, attr, ts):
            return None
        return msg

    def get_delete_event(self, classname, node, vnid, addr, ts):
        # return an eptMsgWorkEpmEvent with status 'delete' for provided node+vnid+addr
        msg = eptMsgWorkEpmEvent(addr, "worker", {}, None, fabric=self.fabric)
        msg.status = "deleted"
        msg.node = node
        msg.vnid = vnid
        msg.ts = ts
        if classname == "epmMacEp":
            msg.wt = WORK_TYPE.EPM_MAC_EVENT
            msg.type = "mac"
        elif classname == "epmIpEp":
            msg.wt = WORK_TYPE.EPM_IP_EVENT
            msg.type = "ip"
        elif classname == "epmRsMacEpToIpEpAtt":
            msg.wt = WORK_TYPE.EPM_RS_IP_EVENT
            msg.type = "ip"
            msg.ip = addr
        else:
            logger.warn("unexpected classname for EpmEventParser get_delete_event: %s", classname)
            return None
        return msg

class eptMsgWorkEpmEvent(eptMsgWork):
    """ standardize parsed result for epmMacEp, epmIpEp, and epmRsMacEpToIpEpAtt objects to always
        include all attributes with default of empty string if not present
    """
    def __init__(self, addr, role, data, wt, qnum=1, seq=1, fabric=1):
        # initialize as eptMsgWork with empty data set 
        super(eptMsgWorkEpmEvent, self).__init__(addr, "worker", data, wt, 
                qnum=qnum, seq=seq, fabric=fabric)
        self.ts = float(data.get("ts", 0))
        self.classname = data.get("classname", "")
        self.type = data.get("type", "")
        self.status = data.get("status", "")
        self.flags = data.get("flags", [])
        self.ifId = data.get("ifId", "")
        self.pcTag = int(data.get("pcTag",0))
        self.encap = data.get("encap", "")
        self.ip = data.get("ip", "")
        self.node = int(data.get("node", 0))
        self.vnid = int(data.get("vnid", 0))
        self.vrf = int(data.get("vrf", 0))
        self.bd = int(data.get("bd", 0))

    def parse(self, overlay_vnid, classname, attr, ts):
        # parse event and set data dict to prepare 
        self.classname = classname
        if "dn" not in attr:
            logger.warn("invalid epm attribute (%s): %s", classname, attr)
            return False
        if self.classname == "epmIpEp":
            self.wt = WORK_TYPE.EPM_IP_EVENT
            r1 = epm_reg.search(attr["dn"])
            self.type = "ip"
        elif self.classname == "epmMacEp":
            self.wt = WORK_TYPE.EPM_MAC_EVENT
            r1 = epm_reg.search(attr["dn"])
            self.type = "mac"
        elif self.classname == "epmRsMacEpToIpEpAtt":
            self.wt = WORK_TYPE.EPM_RS_IP_EVENT
            r1 = epm_rsMacToIp_reg.search(attr["dn"])
            self.type = "ip"
            self.ip = r1.group("ip")
        else:
            logger.warn("insupported epmEvent classname (%s): %s", classname, attr)
            return False
        if r1 is None:
            logger.warn("failed to parse epm event for %s: %s", classname, attr["dn"])
            return False

        self.ts = ts
        self.status = attr.get("status", "created")
        # on build, status is empty string, we need assume created if not provided or empty
        if len(self.status) == 0: 
            self.status = "created"
        self.flags = attr.get("flags", "")
        if len(self.flags) == 0: 
            self.flags = []
        else:
            self.flags = self.flags.split(",")
        self.ifId = attr.get("ifId", "")
        try:
            self.pcTag = int(attr.get("pcTag", 0))
        except ValueError as e:
            self.pcTag = 0
        self.node = int(r1.group("node"))
        self.addr = r1.group("addr")

        # either vrf or ovl will always be set. If ovl then use overlay_vnid for vrf
        if r1.group("vrf") is not None:
            self.vrf = int(r1.group("vrf"))
        elif r1.group("ovl") is not None:
            self.vrf = overlay_vnid
        else:
            logger.warn("parse did not match vrf or ovl %s: %s",attr["dn"],r1.groupdict())
            return False

        # optional matches that need to be set empty string if not present
        self.bd = int(r1.group("bd"))   if r1.group("bd") is not None else 0
        self.encap = r1.group("encap")  if r1.group("encap") is not None else ""

        # set vnid to bd or vrf depending on classname
        self.vnid = self.bd if self.classname == "epmMacEp" else self.vrf

        # successful parse
        # logger.debug("parse epm event on %s(%s): %s", self.classname, self.fabric, attr["dn"])
        return True

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "msg_type": self.msg_type.value,
            "seq": self.seq,
            "wt": self.wt.value,
            "addr": self.addr,
            "role": self.role,
            "qnum": self.qnum,
            "fabric": self.fabric,
            "data": {
                "classname": self.classname,
                "type": self.type,
                "ts": self.ts,
                "status": self.status,
                "flags": self.flags,
                "ifId": self.ifId,
                "pcTag": self.pcTag,
                "node": self.node,
                "vrf": self.vrf,
                "bd": self.bd,
                "encap": self.encap,
                "ip": self.ip,
                "vnid": self.vnid,
            }
        })
        return ret

    def __repr__(self):
        return "%s.0x%08x %s %s [ts:%.3f, node:0x%04x, 0x%06x, %s, %s]" % (self.msg_type.value, 
            self.seq, self.fabric, self.wt.value, self.ts, self.node, self.vnid, self.addr, self.ip)

