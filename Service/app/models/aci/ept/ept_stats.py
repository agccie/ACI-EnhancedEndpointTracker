

class EPTWorkerQueueStats(object):
    def __init__(self, name, priority):
        # track queue statistics where:
        #   priority (int) priority of the queue where lowest number is highest priority
        #   seq     (int) last seq id processes
        #   count   (int) total count of messages received per queue
        self.name = name
        self.priority = priority
        self.seq = 0
        self.count = 0


