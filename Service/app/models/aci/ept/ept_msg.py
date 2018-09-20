
import json
import time

class EPTMsg(object):
    """ generic ept job for messaging between workers """
    def __init__(self, msg_type, data={}, seq=1):
        self.msg_type = msg_type
        self.ts = ts
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
        return "%s_%s.%s" % (self.ts, self.msg_type, self.seq)

    @staticmethod
    def parse(data):
        # parse data received on message queue and return corresponding EPMsg
        # allow exception to raise on invalid data
        js = json.loads(data)
        if js["msg_type"] == "hello": 
            return EPTMsgHello.from_msg_json(js)

        return EPTMsg(
                    js["msg_type"], 
                    data=js.get("data", {}),
                    seq = js.get("seq", None)
                )
                
class EPTMsgHello(object):
    """ hello message sent from worker to manager """

    def __init__(self, worker_id, role, queues, start_time, seq=1):
        self.msg_type = "hello"
        self.worker_id = worker_id
        self.role = role
        self.queues = queues            # list of queue names sorted by priority        
        self.start_time = start_time
        self.seq = seq

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
        # return EPTMsgHello object from received msg js
        hello_data = js["data"]
        return EPTMsgHello(
            hello_data["worker_id"],
            hello_data["role"],
            hello_data["queues"],
            hello_data["start_time"],
            seq = js["seq"],
        )

    def __repr__(self):
        return "[%s] %s.%s" % (self.worker_id, self.msg_type, self.seq)
                


