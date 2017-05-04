"""
    Endpoint Job
    @author agossett@cisco.com
"""

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

    @property
    def keystr(self):
        if type(self.key) is dict:
            return "".join(
                ["|%s:%s|" % (k, self.key[k]) for k in sorted(self.key.keys())])
        else:
            return "%s" % self.key

    def __repr__(self):
        return "%s(%s)" % (self.action, self.keystr)

