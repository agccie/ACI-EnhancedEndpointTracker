
from enum import Enum
from enum import unique as enum_unique

import json
import time

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
    FLUSH_FABRIC        = "flush_fabric"    # request from manager to workers to flush fabric from their
                                            # local caches

# static work types sent with MSG_TYPE.WORK
@enum_unique
class WORK_TYPE(Enum):
    WATCH_NODE          = "watch_node"      # a new node has become active/inactive
    FLUSH_CACHE         = "flush_cache"     # flush cache for specific collection and/or dn
    EPM_IP_EVENT        = "epm_ip"          # epmIpEp event
    EPM_MAC_EVENT       = "epm_mac"         # epmMacEp event
    EPM_RS_IP           = "epm_rs_ip"       # epmRsMacEpToIpEpAtt event

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
        return "%s.%s" % (self.msg_type.value, self.seq)

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
        return "[%s] %s.%s" % (self.worker_id, self.msg_type.value, self.seq)

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
        return "%s.%s %s %s" % (self.msg_type.value, self.seq, self.role, self.wt.value)

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
        return eptMsgWork(js["addr"], js["role"], js["data"], WORK_TYPE(js["wt"]),
                qnum = js["qnum"], seq = js["seq"], fabric= js["fabric"])

                


