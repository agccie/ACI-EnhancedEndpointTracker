import json, pytest, time, subprocess, traceback, inspect, re, copy
from app.tasks.ept import utils as ept_utils
from app.tasks.ept import simulator
from app.tasks.ept.simulator import sim_queues

from app.tasks.ept import node_manager
from app.tasks.ept import ep_subscriber
from app.tasks.ept.ep_subscriber import EPSubscriber
from app.tasks.ept.ep_priority_worker import EPPriorityWorker
from app.tasks.ept.ep_worker import EPWorker
from app.tasks.ept.ep_worker import clear_fabric_endpoint
from app.tasks.ept.ep_worker import clear_node_endpoint
from app.tasks.ept.node_manager import Node_Monitor
from app.tasks.ept.ep_job import EPJob
from multiprocessing import Process


from .test_ep import (get_worker, get_priority_worker, get_test_json,
    get_node_monitor, get_subscriber, test_fabric, test_overlay_vnid)


def test_cfd_14_ep_worker_func_watch_stale(app):
    # issue #14 
    # watch_event needs to check for changed calculated attributes
    # When checking for duplicate watch events, only the ts field is examined 
    # (object modified timestamp). This causes new events with only changes in 
    # calculated attributes to be treated as duplicate events.
    # fix - check changes in calculated indexes
    # ip: (4000000/41000000/40.1.1.101) is on node-101
    key = {
        "addr": "40.1.1.101",
        "vnid": "4000000",
        "type": "ip",
        "fabric": test_fabric,
    }
    dn="topology/pod-1/node-103/sys/ctx-[vxlan-4000000]/db-ep/ip-[40.1.1.101]"
    nodes = {
        "101":{
            "dn": dn,
            "status":"modified",
            "rw_bd":"",
            "remote":"102",
            "addr":"40.1.1.101",
            "ts":1516120584.4,
            "pcTag":"32772",
            "bd":"",
            "flags":"ip",
            "vrf":"4000000",
            "expected_remote":"0",
            "encap":"",
            "ifId":"tunnel7",
            "rw_mac":"",
            "_c":"epmIpEp"
        }
    }
    job = EPJob("watch_stale", key, ts=time.time(),data=nodes)
    dut = get_worker()
    dut.watch_event(job)
    wjob = dut.watched[dut.watched.keys()[0]]
    expected_remote = wjob.data["expected_remote"]
    execute_ts = wjob.execute_ts

    # add same event with nothing changed, should still only have 1 watched job   
    job = EPJob("watch_stale", key, ts=time.time(),data=nodes)
    dut.watch_event(job)
    assert len(dut.watched)==1
    wjob = dut.watched[dut.watched.keys()[0]]
    assert execute_ts == wjob.execute_ts
    assert expected_remote == wjob.data["expected_remote"] 

    # update expected_remote (same ts) and should have an updated execute_ts
    # and updated expected_remote
    n = copy.deepcopy(nodes)
    n["101"]["expected_remote"] = "103"
    job = EPJob("watch_stale", key, ts=time.time(),data=n)
    dut.watch_event(job)
    wjob = dut.watched[dut.watched.keys()[0]]
    assert len(dut.watched)==1
    assert execute_ts != wjob.execute_ts
    assert wjob.data["expected_remote"] == "103"
    

    



