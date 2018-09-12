
from pymongo import IndexModel
from pymongo.errors import (DuplicateKeyError, ServerSelectionTimeoutError)
from pymongo import (ASCENDING, DESCENDING)
import logging
import os
import sys
import time
from multiprocessing import Process

# update sys path for importing test classes for app registration
sys.path.append(os.path.realpath("%s/../../" % os.path.dirname(os.path.realpath(__file__))))

# set logger to base app logger  
logger = logging.getLogger("app")

from app import create_app
from app.models.rest import registered_classes
from app.models.rest import Universe
from app.models.utils import pretty_print
from app.models.utils import get_db
from app.models.utils import setup_logger
from app.models.aci.ept.common import get_ipv4_prefix
from app.models.aci.ept.common import get_ipv4_string
from app.models.aci.ept.common import get_ipv6_prefix
from app.models.aci.ept.common import get_ipv6_string
from app.models.aci.ept.common import get_mac_string
from app.models.aci.fabric import Fabric
from app.models.aci.ept.common import get_ipv4_string, get_ipv6_string
from app.models.aci.ept.epg import eptEpg
from app.models.aci.ept.history import eptHistory
from app.models.aci.ept.node import eptNode
from app.models.aci.ept.subnet import eptSubnet
from app.models.aci.ept.tunnel import eptTunnel
from app.models.aci.ept.vnid import eptVnid
from app.models.aci.ept.vpc import eptVpc
db = None

class Subnet(object):
    def __init__(self, addr, mask, subnet_type, vrf, bd, prefix):
        self.addr = addr
        self.mask = mask
        self.type = subnet_type
        self.bd = bd
        self.vrf = vrf
        self.prefix = prefix
        self.max_ip = self.addr + 10    # don't think we have more than 10 per prefix
        self.next_ip = self.addr + 1
        if self.type == "ipv4":
            self.formatter = get_ipv4_string
        else:
            self.formatter = get_ipv6_string

    def get_next_ip(self):
        # return next available IP in subnet with wrap
        # returns tuple (vrf, ip)
        self.next_ip += 1
        if self.next_ip > self.max_ip:
            self.next_ip = self.addr + 1
        return (self.vrf, self.formatter(self.next_ip))

class Subnets(object):
    # subnet/bd allocator
    def __init__(self):
        self.subnets = []
        self.subnet_ptr = 0

    def add_subnet(self, subnet):
        self.subnets.append(subnet)

    def get_next_ip(self):
        self.subnet_ptr+= 1
        if self.subnet_ptr>= len(self.subnets):
            self.subnet_ptr = 0
        return self.subnets[self.subnet_ptr].get_next_ip()


def dummy_event(history, fabric, vnid, addr):
    # do db lookup on dummy event, no analysis, just return
    db_key = {"fabric":fabric, "vnid":vnid,"addr":addr}
    count = 0
    db.ept.history.update_many(db_key, {"$set":{"is_stale":False}})
    for c in history.find(db_key, {"events":{"$slice":1}}):
        count+=1

def dummy_work(subnets, count):
    # perform dummy_event lookup against subnets 'count' times and print final
    logger.debug("staring worker!")
    db = get_db(uniq=True,overwrite_global=True)
    history = db[eptHistory._classname]
    ts = time.time()
    for i in xrange(0, count):
        (vrf, ip) = subnets.get_next_ip()
        dummy_event(history, fabric, vrf, ip)

    total_time = time.time() - ts
    logger.debug("completed %s lookups, time: %0.3f, avg: %0.6f, jobs/sec: %0.6f", count, total_time,
        total_time/count, count/total_time)



if __name__ == "__main__":

    # db updates through environment settings - required before initializing db
    os.environ["MONGO_HOST"] = "localhost"
    os.environ["MONGO_PORT"] = "27017"
    os.environ["MONGO_DBNAME"] = "scaledb1"

    fabric = "esc-aci-fab4"

    # force logging to stdout
    setup_logger(logger, stdout=True)

    app = create_app("config.py")
    db = get_db()

    vnids = {}  # index by vnid with ptr to eptVnid object

    logger.debug("reading vnids")
    for v in eptVnid.load(_bulk=True):
        vnids[v.vnid] = v

    # get list of subnets
    logger.debug("reading subnets")
    subnets = Subnets()
    collection = db[eptSubnet._classname]
    for r in collection.find({}):
        addr = eptSubnet.byte_list_to_long(r["addr_byte"])
        mask = eptSubnet.byte_list_to_long(r["mask_byte"])
        r["addr"] = addr
        r["mask"] = mask
        # get vrf from bd vnid
        if r["bd"] not in vnids:
            logger.error("unknown bd vnid: 0x%x", r["bd"])
            sys.exit(1)
        vrf = vnids[r["bd"]].vrf
        subnets.add_subnet(Subnet(addr, mask, r["type"], vrf, r["bd"], r["subnet"]))

    # drop vnids, don't need them in memory anymore
    vnids = {}

    logger.debug("subnets: %s", len(subnets.subnets))


    # walk through subnets and get
    # generate random events to measure amount of time to perform x lookups
    worker_count = 5
    job_count = 100000
    workers = {}
    ts = time.time()
    for i in xrange(0, worker_count):
        p = Process(target=dummy_work, args=(subnets, job_count))
        p.start()
        workers[p.pid] = p
        # walk subnets forward by count
        for x in xrange(0, job_count): subnets.get_next_ip()

    # wait for all workers to stop
    for pid in workers:
        workers[pid].join()

    total_time = time.time() - ts
    logger.debug("total time: %s, total count: %d, avg: %0.6f", total_time,
        worker_count*job_count, total_time/(worker_count*job_count))
    logger.debug("avg jobs/sec %0.3f", 1.0*worker_count*job_count/total_time)



    # get all vnid, addr that exists
    """
    ts = time.time()
    logger.debug("full read start")
    logger.debug("total: %s", collection.find({"fabric":"esc-aci-fab4"}).count())
    collection = db[eptHistory._classname]
    addr = {}
    projection = {
        "node": 1,
        "addr": 1,
        "vnid": 1,
        "type": 1
    }
    batch_size = [100, 500, 1000, 2500, 5000, 7500, 10000, 12500, 15000]
    batch_size = [15000]
    for b in batch_size:
        total_count = 0
        #for r in collection.find({"fabric":"esc-aci-fab4", "events.0.status":{"$ne":"deleted"}}, projection):
        for r in collection.find({"fabric":"esc-aci-fab4", "events.0.status":{"$ne":"deleted"}}, projection).batch_size(b):
            total_count+=1
            if total_count%250000 == 0:
                logger.debug("count: %s", total_count)
        logger.debug("full read complete. count: %s, time: %s, batch-size: %d", total_count, time.time()-ts, b)
    """




