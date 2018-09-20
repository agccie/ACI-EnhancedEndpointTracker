
import json
import time

class eptMsg(object):
    """ generic ept job for messaging between workers """
    def __init__(self, msg_type, data={}, seq=1):
        self.msg_type = msg_type
        self.data = data
        self.seq = seq

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "msg_type": self.msg_type,
            "data": self.data,
            "seq": self.seq,
        })

    def __repr__(self):
        return "%s.%s" % (self.msg_type, self.seq)

    @staticmethod
    def parse(data):
        # parse data received on message queue and return corresponding EPMsg
        # allow exception to raise on invalid data
        js = json.loads(data)
        if js["msg_type"] == "work":
            return eptMsgWork.from_msg_json(js)
        elif js["msg_type"] == "hello": 
            return eptMsgHello.from_msg_json(js)

        return eptMsg(
                    js["msg_type"], 
                    data=js.get("data", {}),
                    seq = js.get("seq", None)
                )

class eptMsgHello(object):
    """ hello message sent from worker to manager """

    def __init__(self, worker_id, role, queues, start_time, seq=1):
        self.msg_type = "hello"
        self.worker_id = worker_id
        self.role = role
        self.queues = queues            # list of queue names sorted by priority        
        self.start_time = start_time
        self.seq = seq

    def __repr__(self):
        return "[%s] %s.%s" % (self.worker_id, self.msg_type, self.seq)

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "msg_type": self.msg_type,
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

    def __init__(self, addr, role, data, qnum=1, seq=1):
        self.msg_type = "work"
        self.addr = addr
        self.role = role
        self.qnum = qnum
        self.data = data
        self.seq = seq

    def __repr__(self):
        return "%s.%s %s" % (self.msg_type, self.seq, self.role)

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "msg_type": self.msg_type,
            "seq": self.seq,
            "data": self.data,
            "addr": self.addr,
            "role": self.role,
            "qnum": self.qnum,
        })

    @staticmethod
    def from_msg_json(js):
        # return eptMsgWork object from received msg js
        return eptMsgWork(js["addr"], js["role"], js["data"], js["qnum"], js["seq"])

                


