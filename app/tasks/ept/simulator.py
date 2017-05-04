"""
    EPT Simulator
    @author agossett@cisco.com
"""

import json, re, time, traceback, hashlib
from multiprocessing import Queue as mQueue
from Queue import Empty
try: import cPickle as pickle
except ImportError: import pickle

# setup logging for simulator
import logging
from . import utils as ept_utils
logger = logging.getLogger(__name__)
ept_utils.setup_logger(logger)

class ApicSimulatorException(Exception):
    def __init__(self, value): self.value = value
    def __str__(self): return repr(self.value)

class ApicSimulator(object):
    """ ApicSimulator object used for simulator a subscription or API call
        to apic/node
    """
    def __init__(self):
        self.ipaddr = "127.0.0.1"
        self.subscribe_urls = {} # just ensure subscription setup correctly
        self.events = {}
        self.ready_events = {}
        self.event_count = 0
        self.ready_event_count = 0
        self.start_time = None


    def start(self):
        # start simulation (should be called after all events have been added)
        self.start_time = time.time()
        logger.debug("setting start timer to %s" % self.start_time)

    def clear(self):
        # clear all current events and start timestamp - used between tests
        self.subscribe_urls = {}
        self.events = {}
        self.ready_events = {}
        self.event_count = 0
        self.ready_event_count = 0
        self.start_time = None

    def login(self):
        logger.debug("simulator login")
        return getResult(ok=True)
    
    def close(self):
        logger.debug("simulator close")
        return

    def refresh_login(self):
        logger.debug("simulator refreshing login")
        return getResult(ok=True)

    def subscribe(self, url, new_only=False):
        #logger.debug("simulator subscribe url:%s" % url)
        if url not in self.subscribe_urls:
            self.subscribe_urls[url] = 1
        return getResult(ok=True)

    def get(self, url, **kwargs):
        """ simulate get requests for particular url. If url does not exists
            then empty result returned.
            result object needs to have 
        """
        #logger.debug("simulator get url:%s" % url)
        self._ready_events(url, subscribe=True)
        if url in self.ready_events and len(self.ready_events[url])>0:
            self.ready_event_count-=1
            return getResult(ok=True, data=self.ready_events[url].pop(0))
    
        # doesn't make sense for simulator to return empty data, generate
        # 404 not found error for get requests that werent setup correctly
        return getResult(ok=False, status_code=404)

    def get_event_count(self, url):
        #logger.debug("simulator get_event_count url:%s" % url) 
        self._check_subscribed(url)
        self._ready_events(url, subscribe=True)

        # if there are no more events in the simulation, kill it by
        # returning -1 for event_count
        ec = 0
        if url in self.ready_events: ec = len(self.ready_events[url])
        if ec>0: return ec
        elif ec==0 and self.ready_event_count==0 and self.event_count==0:
            return -1
        else:
            return 0

    def has_events(self, url):
        #logger.debug("simulator has_events url:%s" % url)
        return self.get_event_count(url)>0
    
    def get_event(self, url):
        #logger.debug("simulator get_event url:%s" % url)
        # should never request an event if did not first confirm there are
        # events ready. So throw exception if there are none available
        if not self.has_events(url):
            raise ApicSimulatorException("no events available for url")
        self.ready_event_count-=1
        return self.ready_events[url].pop(0)

    def add_event(self, url, **kwargs):
        # add a simulation subscription/get event.  Note, if an event already
        # exists for particular url, it is appended as the 'next' event. Script
        # assumes that user adds events in correct order.
        # Each event has a start/end timestamp. For subscriptions, end 
        # timestamps are ignored, the events are simply queued to simulate 
        # 'queue' of events.
        # for get requests, the request must come in within start/end time
        # frame.
        # set either value to None to imply any time is valid.
        # once event is serviced, it is poped from the url list.
        #
        # kwargs:   
        #   event - object (dict) to return when event is simulated
        #   url   - url for subscription to send event or url to respond for
        #           for get requests
        #   start - start time (from beginning of simulation) that event will
        #           be returned via subscription or get request
        #   end   - end times (from beginning of simulation) that event will
        #           be returned via subscription or get request
        event = kwargs.get("event", {})
        start = kwargs.get("start", None)
        end = kwargs.get("end", None)
        if url not in self.events: 
            self.events[url] = []
            self.ready_events[url] = []
        self.events[url].append({
            "event": event,
            "start": start,
            "end": end
        })
        self.event_count+= 1

    def add_event_file(self, filename):
        # read file with list of event objects
        try:
            with open(filename, "r") as f:
                js = json.load(f)
                if "events" not in js:
                    err = "expected 'events' attribute not found in %s" %(
                        filename)
                    raise ApicSimulatorException(err)
                js = js["events"]
                if type(js) is not list:
                    err = "eventfile(%s) should be list, received (%s)" %(
                        filename, str(type(js)))
                    raise ApicSimulatorException(err)
                event_count = 0
                for event in js:
                    if type(event) is not dict:
                        err = "event(%s) in eventfile(%s) should be dict, " % (
                            event_count, filename)
                        err+= "received (%s)" % str(type(event))
                        raise ApicSimulatorException(err)
                    # require at least 'url' and 'event' attributes 
                    if "url" not in event or "event" not in event:
                        err = "event(%s) in eventfile(%s) missing " % (
                            event_count, filename)
                        err+= "required attribute(s) 'url' and 'event'"
                        raise ApicSimulatorException(err)
                    _url = event["url"]
                    _event = event["event"]
                    _start = event["start"] if "start" in event else None
                    _end = event["end"] if "end" in event else None
                    self.add_event(_url, event=_event, start=_start, end=_end)
                    event_count+= 1
        except Exception as e:
            err = "failed to read events from event_file: %s" % filename
            raise ApicSimulatorException("exception: %s, %s" % (e, err))

    def _check_subscribed(self, url):
        # subscription never started... exception
        if url not in self.subscribe_urls:
            raise ApicSimulatorException("subscription never created")

    def _ready_events(self, url, subscribe=False):
        # move events from events simulation list to ready_events list
        # if subscribe set to true, then ignore end timestamp
        if self.start is None: 
            raise ApicSimulatorException("simulater never started")
        if url not in self.events: return
        event_time = abs(time.time() - self.start_time)
        event_indexes = [] # list of indexes to move from events to ready
        miss_indexes = []  # list of indexes to remove from events (missed)
        i = 0
        for e in self.events[url]:
            if e["start"] is None or event_time>=e["start"]:
                if subscribe:
                    event_indexes.append(i)
                elif e["end"] is None or event_time<=e["end"]:
                    # non-subscription can only add single event
                    event_indexes.append(i)
                    break
                else:
                    # non-subscription with current time > end, remove
                    # from events (missed event)
                    miss_indexes.append(i)
            i+=1
     
        # walk in reverse order to allow pop without corrupting lower indexes
        buff = [] 
        for i in reversed(xrange(0, len(self.events[url]))):
            if i in event_indexes:
                e = self.events[url].pop(i)
                self.event_count-=1
                self.ready_event_count+=1
                buff.append(e["event"])
            elif i in miss_indexes:
                e = self.events[url].pop(i)
                self.event_count-=1
                logger.debug("missed event [%s, %s]" % (url, e))
        
        # added in reverse order, append to list with another reverse
        self.ready_events[url]+= reversed(buff)
        

class getResult(object):
    """ simulated result object returned by login and get requests """
    def __init__(self, ok=True, data={}, status_code=200):
        self.ok = ok
        self.status_code = status_code
        self.data = data
    
    def json(self): return self.data

from contextlib import contextmanager
@contextmanager
def Connection(name=None):
    #logger.debug("opening connection: %s" % name)
    try:
        yield
    finally: pass
    #logging.debug("closing connection: %s" % name)  
 

# each queue adds itself to result queue so we can read all queues created
# during simulation
sim_queues = {}

class Queue(object):
    def __init__(self, qname, **kwargs):
        self.qname = qname
        if self.qname not in sim_queues:
            sim_queues[self.qname] = []
        sim_queues[self.qname].append(self)
        self.jobs = []

    @property
    def count(self):
        return len(self.get_jobs())

    def enqueue(self, *args, **kwargs):
        # for now, simulator expects only args to be provided or optional
        # depends_on kwarg
        # arg 0 = function
        # arg 1 = function args (key)
        depends_on = kwargs.get("depends_on", None)
        if len(args) == 2:
            logger.debug("enqueue on %s: %s" % (self.qname, args[1]))
            j = sJob(function=args[0],key=args[1], depends_on=depends_on)
            self.jobs.append(j)
            return j
        else:
            logger.warn("not enqueuing invalid arguments(%s): %s" % (len(args),
                args))

    def get_jobs(self, offset=0, length=-1):
        # get slice of jobs on queue
        jobs = []
        qcount = 0
        if self.qname in sim_queues:
            for q in sim_queues[self.qname]:
                if qcount>= offset:
                    if length>0 and len(jobs)>=length: break
                    jobs+= q.jobs
                qcount+= len(q.jobs)
        return jobs

class sJob(object):
    def __init__(self, function=None, key=None, depends_on=None):
        self.function = function
        self.key = key
        self._id = hashlib.md5("%s%f"%(self.function,time.time())).hexdigest()
        self.is_queued = True
        self.is_started = False
        self.is_failed = False
        self.is_finished = False
        self.depends_on = depends_on
        # pickle data to be consistent with rq pickling
        self.data = pickle.dumps([0,0,[self.key]])

    def get_id(self): return self._id
       
    def __repr__(self):
        d = "-"
        if self.depends_on is not None:
            if hasattr(self.depends_on, "_id"): d = self.depends_on._id
            else: d = self.depends_on
        return "id: %s, [q:%r,s:%r,fa:%r,fi:%r], key:%s, func:%s, depends:%s"%(
            self._id, self.is_queued, self.is_started, self.is_failed,
            self.is_finished,self.key, self.function.__name__, d)
            
class mQueue(object):
    # simulate multiprocessing queue
    def __init__(self):
        self.jobs = []

    def get(self):
        if len(self.jobs) == 0: 
            # wait forever
            while 1: time.sleep(1)
        #logger.debug("simulator get: %s" % self)
        j = self.jobs.pop(0)
        #logger.debug("simulator removed index 0: %s" % j)
        #logger.debug("simulator new: %s" % self)
        return j

    def get_nowait(self): 
        if len(self.jobs) == 0: raise Empty("queue is empty")
        return self.get()
        
    def put(self, obj): 
        #logger.debug("simulator put(%s) on %x" % (obj,id(self)))
        self.jobs.append(obj)
        #logger.debug("simulator new: %s" % self)

    def put_nowait(self, obj): return self.put(obj)

    def qsize(self): return len(self.jobs)
        
    def empty(self): return len(self.jobs)<=0
    
    def __repr__(self):
        return "%x: [%s]" % (id(self), ",".join(["%s" % j for j in self.jobs]))

class Connection(object):
    # simulate connection object
    def __init__(self, hostname):
        self.cmds = {}
        self.executed_cmds = mQueue()
        self.default = None
        self.output= ""
        self.hostname = hostname
        self.username = ""
        self.password = ""
        self.prompt = ""
        self.protocol = "ssh"
        self.log = None

    def add_cmd(self, cmd, output):
        # add a single command to cmds dict
        logger.debug("adding command: %s" % cmd)
        self.cmds[cmd] = output

    def add_cmds(self, commands):
        # receives dict with 'commands' list where each command contains two
        # attributes 'cmd' and 'output'
        if "commands" in commands:
            for c in commands["commands"]:
                if "cmd" in c and "output" in c: 
                    self.add_cmd(c["cmd"], c["output"])

    def clear(self):
        self.cmds = {}
        while self.executed_cmds.qsize()>0:
            try: self.executed_cmds.get_nowait()
            except Empty: break
        self.default = None

    def login(self, max_attempts=7, timeout=17):
        return True

    def remote_login(self, command, **kwargs):
        self.executed_cmds.put(command)
        return True

    def cmd(self, command, **kargs):
        # very basic simulation, if simulator setup command then set output to
        # result and return 'prompt'.  Else, return timeout
        self.executed_cmds.put(command)
        if command in self.cmds:
            self.output = self.cmds[command]
            return "prompt"
        elif self.default is not None:
            self.output = self.default
            return "prompt"
        else:
            logger.warn("command %s not found, returning timeout" % command)
            self.output = ""
            return "timeout"
        

