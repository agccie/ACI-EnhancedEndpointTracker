
import json
import time

class EPJob(object):
    """ endpoint job """
    def __init__(self, action, key, ts=None, data={}, execute_ts=None):
        self.action = action
        self.key = key
        self.ts = ts
        self.execute_ts = execute_ts
        self.data = data
        if self.ts is None: self.ts = time.time()
        self._keystr = None

    @property
    def keystr(self):
        if self._keystr is not None: return self._keystr
        if type(self.key) is dict:
            self._keystr =  "".join(["|%s:%s|" % (k, self.key[k]) for k in sorted(self.key.keys())])
        else:
            self._keystr = "%s" % self.key
        return self._keystr

    def jsonify(self):
        """ jsonify for transport across messaging queue """
        return json.dumps({
            "action": self.action,
            "key": self.key,
            "ts": self.ts,
            "execute_ts": self.execute_ts,
            "data": self.data,
        })

    def __repr__(self):
        return "%s(%s)" % (self.action, self.keystr)

    @staticmethod
    def parse(data):
        # parse data received on message queue and return corresponding EPJob
        # allow exception to raise on invalid data
        js = json.loads(data)
        return EPJob(js["action"], js["key"], data=js.get("data", {}),
                    ts = js.get("ts", None), 
                    execute_ts = js.get("execute_ts", None)
                )
                
