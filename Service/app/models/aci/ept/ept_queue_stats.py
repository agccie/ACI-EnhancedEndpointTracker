
from ... rest import Rest
from ... rest import api_callback
from ... rest import api_register
from ... rest import api_route
from ... utils import get_db
from flask import jsonify

import copy
import logging
import time

# module level logging
logger = logging.getLogger(__name__)

stats_queue_meta = {
    "timestamp": {
        "type": float,
        "description": "epoch timestamp when stats where collected",
    },
    "total_tx_msg": {
        "type": int,
        "description": "total number of transmitted messages at time of collection",
    },
    "total_rx_msg": {
        "type": int,
        "description": "total number of received messages at time of collection",
    },
    "tx_msg": {
        "type": int,
        "description": "number of transmitted messages on queue within interval",
    },
    "rx_msg": {
        "type": int,
        "description": "number of received messages on queue within interval",
    },
    "tx_msg_rate": {
        "type": float,
        "description": "transmit message rate over the last collection interval",
    },
    "rx_msg_rate": {
        "type": float,
        "description": "receive message rate over the last collection interval",
    },
}
stats_queue_meta_with_qlen = copy.deepcopy(stats_queue_meta)
stats_queue_meta_with_qlen["qlen"] = {
    "type": int,
    "description": "number of messages in queue at time of collection",
}

@api_register(path="ept/queue")
class eptQueueStats(Rest):
    """ historical statistics for messages sent between manager/worker processes. Each process can
        have one or more queues and this object will track aggregate and relative rates on various
        intervals. This is useful to understand the number of events processed by the application
        on a per minute/hour/daily basis.
    """

    STATS_SLICE = 72            # maximum length of stats queue 
    STATS_SLICE_MINUTES = 360   # length of stats queue for minute interval
    STATS_INTERVAL = 60.0       # stats collection interval
    INTERVALS = [
        ("stats_1min", 60, STATS_SLICE_MINUTES),
        ("stats_5min", 300, STATS_SLICE),
        ("stats_15min", 900, STATS_SLICE),
        ("stats_1hour", 3600, STATS_SLICE),
        ("stats_1day", 86400, STATS_SLICE),
        ("stats_1week", 604800, STATS_SLICE),
    ]

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }

    META = {
        "proc": {
            "type": str,
            "key": True,
            "key_index": 0,
            "description": "worker or manager process identifier"
        },
        "queue": {
            "type": str,
            "key": True,
            "key_index": 1,
            "description": "queue name"
        },
        "start_timestamp": {
            "type": float,
            "description": "epoch timestamp when process last restarted",
        },
        "total_tx_msg": {
            "type": int,
            "description": """
            total number of transmit messages on queue since uptime of the process. Note these
            counters are reset if process is restarted.
            """,
        },
        "total_rx_msg": {
            "type": int,
            "description": """
            total number of receive messages on queue since uptime of the process. Note these
            counters are reset if process is restarted.
            """,
        },
        "stats_1min": {
            "type": list,
            "subtype": dict,
            "description": """
            1 min interval statistics for this queue with most recent events at the top of the list
            """,
            "meta": stats_queue_meta_with_qlen,
        },
        "stats_5min": {
            "type": list,
            "subtype": dict,
            "description": """
            5 min interval statistics for this queue with most recent events at the top of the list
            """,
            "meta": stats_queue_meta,
        },
        "stats_15min": {
            "type": list,
            "subtype": dict,
            "description": """
            15 min interval statistics for this queue with most recent events at the top of the list
            """,
            "meta": stats_queue_meta,
        },
        "stats_1hour": {
            "type": list,
            "subtype": dict,
            "description": """
            1 hour interval statistics for this queue with most recent events at the top of the list
            """,
            "meta": stats_queue_meta,
        },
        "stats_1day": {
            "type": list,
            "subtype": dict,
            "description": """
            1 day interval statistics for this queue with most recent events at the top of the list
            """,
            "meta": stats_queue_meta,
        },
        "stats_1week": {
            "type": list,
            "subtype": dict,
            "description": """
            1 week interval statistics for this queue with most recent events at the top of the list
            """,
            "meta": stats_queue_meta,
        },
    }

    def init_queue(self):
        # initialize counters (which occurs anytime corresponding process restarts)
        logger.debug("initialize queue: %s, %s", self.proc, self.queue)
        self.start_timestamp = time.time()
        #self.total_tx_msg = 0
        #self.total_rx_msg = 0
        self.save(refresh=True)
        self.db = get_db()

    def collect(self, qlen=0):
        # consuming process should be incrementing total tx/rx as the queue is utilized. However,
        # when it's time to push the statistics to historical list this function is called...
   
        # save total rx/tx values before they are lost with db reload
        total_tx = self.total_tx_msg
        total_rx = self.total_rx_msg

        # refresh state from db and calculate stats for each measurement inteval
        self.reload()
        ts = time.time()
        update = {}
        for (stat_name, delta, stats_slice) in eptQueueStats.INTERVALS:
            stats = getattr(self, stat_name)
            if ts - self.start_timestamp > delta and \
                (len(stats)==0 or ts - stats[0]["timestamp"] >= delta):
                record = {
                    "timestamp": ts,
                    "total_tx_msg": total_tx,
                    "total_rx_msg": total_rx,
                    "tx_msg": total_tx,
                    "rx_msg": total_rx,
                    "tx_msg_rate": 0,
                    "rx_msg_rate": 0,
                }
                # qlen only used by 1 minute stats collection
                if stat_name == "stats_1min": record["qlen"] = qlen
                true_delta = delta
                if len(stats) > 0:
                    record["tx_msg"] = abs(total_tx - stats[0]["total_tx_msg"])
                    record["rx_msg"] = abs(total_rx - stats[0]["total_rx_msg"])
                    true_delta = abs(ts - stats[0]["timestamp"])
                if true_delta > 0:
                    record["tx_msg_rate"] = float(record["tx_msg"]) / true_delta
                    record["rx_msg_rate"] = float(record["rx_msg"]) / true_delta
                stats.insert(0, record)
                setattr(self, stat_name, stats[0:stats_slice])

        # save db update 
        self.total_tx_msg = total_tx
        self.total_rx_msg = total_rx
        self.save(refresh=False)
