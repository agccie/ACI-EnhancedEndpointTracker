
from flask import request, abort, g, current_app
from utils import (aes_encrypt, get_user_data, MSG_403)
from pymongo.errors import DuplicateKeyError
import logging

from .roles import Roles
from .users import Users
from .rest import Rest, check_user_access

class EP_Settings(Rest):
    """ ep_setup REST class """

    # module level logger
    logger = logging.getLogger(__name__)

    # meta data and type that are exposed via read/write 
    META = {
        "fabric":{
            "type":str, "default":"", "read":True, "write":False, 
            "regex":"^[a-zA-Z0-9\-\.:_]{1,64}$"
            },
        "apic_username":{
            "type":str, "default":"admin", "read":True, "write":True, 
            "regex":"^[a-zA-Z0-9\-_\.@]{1,128}$"
        },
        "apic_password":{
            "type":str, "default":"","read":False,"write":True
        },
        "apic_hostname":{
            "type":str, "default":"","read":True,"write":True
        },
        "apic_cert": {
            "type":str,"default":"","read":True,"write":True
        },
        "ssh_username":{
            "type":str, "default":"", "read":True, "write":True, 
            "regex":"^[a-zA-Z0-9\-_\.@]{0,128}$"
        },
        "ssh_password":{
            "type":str, "default":"","read":False,"write":True
        },
        "ssh_access_method":{
            "type":str, "read":True,"write":True, "default":"address",
            "values":["oobMgmtAddr", "inbMgmtAddr", "address"]
            },
        "email_address": {
            "type":str, "default":"", "read":True, "write":True, 
            "regex":"(^$|^[a-zA-Z0-9\-_\.@\+]+$)"
        },
        "syslog_server":{
            "type":str, "default":"","read":True,"write":True
        },
        "syslog_port":{
            "type":int, "default":514,"read":True,"write":True
        },
        "notify_move_email":{
            "type":bool, "default":True,"read":True,"write":True
        },
        "notify_stale_email":{
            "type":bool, "default":True,"read":True, "write":True
        },
        "notify_offsubnet_email":{
            "type":bool, "default":True,"read":True, "write":True
        },
        "notify_move_syslog": {
            "type":bool, "default":True,"read":True, "write":True
        },
        "notify_stale_syslog": {
            "type":bool, "default":True,"read":True, "write":True
        },
        "notify_offsubnet_syslog": {
            "type":bool, "default":True,"read":True, "write":True
        },
        "auto_clear_stale": {
            "type":bool,"read":True,"write":True,"default":False
        },
        "auto_clear_offsubnet": {
            "type":bool,"read":True,"write":True,"default":False
        },
        "analyze_move": {
            "type":bool,"default":True,"read":True,"write":True
        },
        "analyze_stale": {
            "type":bool,"default":True,"read":True,"write":True
        },
        "analyze_offsubnet": {
            "type":bool,"default":True,"read":True,"write":True
        },
        "max_ep_events":{
            "type":int,"default":64,"read":True,"write":False,
            "min_val":1, "max_val":1024
        },
        "max_workers":{
            "type":int,"default":6,"read":True,"write":False,
            "min_val":1, "max_val":128
        },
        "max_jobs":{
            "type":int,"default":65536,"read":True,"write":False,
            "min_val":1024, "max_val":65536
        },
        "fabric_events": {
            "type":list, "default":[],"read":True,"write":False
        },
        "fabric_events_count":{
            "type":int,"default":0,"read":True, "write":False
        },
        "max_fabric_events": {
            "type":int,"default":1024,"read":True, "write":True
        },
        "trust_subscription": {
            "type":str,"default":"auto","read":True, "write":True,
            "values":["yes","no","auto"]
        },
        "fabric_warning": {
            "type":str,"default":"","read":True,"write":False
        }
    }

    def __init__(self):
        super(Rest, self).__init__()

    @classmethod
    def create(cls):
        """ api call - create new fabric settings """

        # check if user provided apic password, if so encrypt it
        override_attr = {}
        data = get_user_data(["fabric"])
        fabric = data["fabric"]
        if "apic_password" in data:
            override_attr["apic_password"] = aes_encrypt(data["apic_password"])
            if override_attr["apic_password"] is None:
                abort(500, "encryption block failed")
        if "ssh_password" in data:
            override_attr["ssh_password"] = aes_encrypt(data["ssh_password"])
            if override_attr["ssh_password"] is None:
                abort(500, "encryption block failed")

        Rest.create.__func__(cls, current_app.mongo.db.ep_settings,
            rule_dn = "/ept/settings/",
            required_attr = ["fabric"],
            override_attr = override_attr,
        )
        return {"success": True, "fabric": fabric} 

    @classmethod
    def read(cls, fabric=None):
        """ api call - read one or more settings from database """

        if fabric is not None: read_one = ("fabric", fabric)
        else: read_one = None

        return Rest.read.__func__(cls, current_app.mongo.db.ep_settings,
            rule_dn = "/ept/settings/",
            read_one = read_one,
            sort = "fabric"
        )

    @classmethod
    def update(cls, fabric):
        """ api call - update ep_settings """

        # check if user provided apic password, if so encrypt it
        override_attr = {}
        data = get_user_data([])
        if "apic_password" in data:
            override_attr["apic_password"] = aes_encrypt(data["apic_password"])
            if override_attr["apic_password"] is None:
                abort(500, "encryption block failed")
        if "ssh_password" in data:
            override_attr["ssh_password"] = aes_encrypt(data["ssh_password"])
            if override_attr["ssh_password"] is None:
                abort(500, "encryption block failed")

        # perform update (aborts on error)
        update = Rest.update.__func__(cls, current_app.mongo.db.ep_settings,
            rule_dn = "/ept/settings",
            update_one = ("fabric", fabric),
            override_attr = override_attr,
        )
        return {"success": True}

    @classmethod
    def delete(cls, fabric):
        """ api call - delete ep_settings """

        # perform delete operation
        Rest.delete.__func__(cls, current_app.mongo.db.ep_settings,
            rule_dn = "/ept/settings/",
            delete_one = ("fabric", fabric),
        )

        # manually delete all entries matching this fabric from other tables
        collections = [
            current_app.mongo.db.ep_epgs,
            current_app.mongo.db.ep_history,
            current_app.mongo.db.ep_moves,
            current_app.mongo.db.ep_nodes,
            current_app.mongo.db.ep_stale,
            current_app.mongo.db.ep_tunnels,
            current_app.mongo.db.ep_vnids,
            current_app.mongo.db.ep_vpcs,
            current_app.mongo.db.ep_subnets,
            current_app.mongo.db.ep_offsubnet,
        ]
        for c in collections:
            r = c.delete_many({"fabric":fabric})
        return {"success": True}

class EP_Nodes(Rest):
    """ EP_Nodes REST class """

    # module level logger
    logger = logging.getLogger(__name__)

    # meta data and type that are exposed via read with type and default values
    META = {
        "fabric": {"type":str, "default":"","read":True,"write":False},
        "dn": {"type":str, "default":"","read":True,"write":False},
        "name": {"type":str, "default":"","read":True,"write":False},
        "oobMgmtAddr": {"type":str, "default":"","read":True,"write":False},
        "state": {"type":str, "default":"","read":True,"write":False},
        "role": {"type":str, "default":"","read":True,"write":False},
        "address": {"type":str, "default":"","read":True,"write":False},
        "systemUptime": {"type":str, "default":"","read":True,"write":False},
        "id": {"type":str, "default":"","read":True,"write":False},
        "nodes": {"type": list, "default":[], "read":True, "write":False, 
                    "subtype": str},
    }

    def __init__(self):
        super(Rest, self).__init__()

    @classmethod
    def create(cls):
        """ block create requests to settings (not implemented) """
        abort(400, "cannot create new ep_nodes")

    @classmethod
    def read(cls):
        """ api read call """

        r = Rest.read.__func__(cls, current_app.mongo.db.ep_nodes,
            rule_dn = "/ept/",
        )
        return {"nodes": r["ep_nodes"]}

    @classmethod
    def update(cls):
        """ block update """
        abort(400, "cannot update ept_nodes")

    @classmethod
    def delete(cls):
        """ block delete requests to settings (not implemented) """
        abort(400, "cannot delete ept_nodes")

class EP_Tunnels(Rest):
    """ EP_Tunnels REST class """

    # module level logger
    logger = logging.getLogger(__name__)

    # meta data and type that are exposed via read with type and default values
    META = {
        "fabric": {"type":str, "default":"","read":True,"write":False},
        "dn": {"type":str, "default":"","read":True,"write":False},
        "dest": {"type":str, "default":"","read":True,"write":False},
        "operSt": {"type":str, "default":"","read":True,"write":False},
        "src": {"type":str, "default":"","read":True,"write":False},
        "tType": {"type":str, "default":"","read":True,"write":False},
        "type": {"type":str, "default":"","read":True,"write":False},
        "node": {"type":str, "default":"","read":True,"write":False},
        "id": {"type":str, "default":"","read":True,"write":False},
    }

    def __init__(self):
        super(Rest, self).__init__()

    @classmethod
    def create(cls):
        """ block create requests to settings (not implemented) """
        abort(400, "cannot create new ep_tunnels")

    @classmethod
    def read(cls):
        """ api read call """

        r = Rest.read.__func__(cls, current_app.mongo.db.ep_tunnels,
            rule_dn = "/ept/",
        )
        return {"tunnels": r["ep_tunnels"]}

    @classmethod
    def update(cls):
        """ block update """
        abort(400, "cannot update ep_tunnels")

    @classmethod
    def delete(cls):
        """ block delete requests to settings (not implemented) """
        abort(400, "cannot delete ep_tunnels")


class EP_History(Rest):
    """ EP_History REST class """

    # module level logger
    logger = logging.getLogger(__name__)

    # meta data and type that are exposed via read with type and default values
    META = {
        "fabric": {"type":str, "default":"","read":True,"write":False},
        "addr": {"type":str, "default":"","read":True,"write":False},
        "vnid": {"type":str, "default":"","read":True,"write":False},
        "node": {"type":str, "default":"","read":True,"write":False},
        "type": {"type":str, "default":"","read":True,"write":False},
        "is_stale": {"type":bool, "default":False,"read":True,"write":False},
        "is_offsubnet":{"type":bool,"default":False,"read":True,"write":False},
        "events": {"type":list, "default":[],"read":True,"write":False},
    }

    def __init__(self):
        super(Rest, self).__init__()

    @classmethod
    def create(cls):
        """ block create requests (not implemented) """
        abort(400, "cannot create new ep_history")

    @classmethod
    def read(cls, fabric=None, addr=None, vnid=None, node=None, search=None,
            limit=None):
        """ api read call """
        # build filter based on addr/vnid/node
        filters = {}
        if fabric is not None: filters["fabric"] = fabric
        if addr is not None: filters["addr"] = addr
        if vnid is not None: filters["vnid"] = vnid
        if node is not None: filters["node"] = node 

        projection = None
        if search is not None:
            # no result returned for empty search
            if len(search) == 0:
                return {"ep_history":[]}

            # filter only on addr not already provided
            filters["addr"] = {"$regex":search, "$options": "i"}
            # if search provided then don't return events...
            projection = ["addr", "vnid", "node", "type","fabric"]
            # enforce search limit
            if limit is None: limit = 50

        r = Rest.read.__func__(cls, current_app.mongo.db.ep_history,
            rule_dn = "/ept/",
            filter_attr = filters,
            projection = projection,
            limit = limit
        )
        return r

    @classmethod
    def count(cls):
        """ api call for total ip/mac count """
        # no aggregate command available in utils or rest, need to manually
        # check user access and perform read directly
        check_user_access(rules=["/ept"], match_all=True, read_required=True,
            cls=cls)

        # aggregate count per fabric, per type, filtered on non-deleted eps
        r = current_app.mongo.db.ep_history.aggregate([
            {"$match":{"events.0.status":{"$ne":"deleted"}}},
            {"$group":{
                "_id":{"fabric":"$fabric","addr":"$addr","type":"$type"}}
            }, 
            {"$group": {
                "_id":{"fabric":"$_id.fabric", "type":"$_id.type"}, 
                "count":{"$sum":1}
            }}
        ], allowDiskUse=True)
        per_fabric = {}
        for entry in r:
            if "count" in entry and "_id" in entry \
                and "type" in entry["_id"] and "fabric" in entry["_id"]:
                fab = entry["_id"]["fabric"]
                if fab not in per_fabric:
                    per_fabric[fab] = {"ip":0, "mac":0, "fabric": fab}
                if entry["_id"]["type"] == "ip":
                    per_fabric[fab]["ip"] = entry["count"]
                elif entry["_id"]["type"] == "mac":
                    per_fabric[fab]["mac"] = entry["count"]
        return {"history": [per_fabric[fab] for fab in per_fabric]}

    @classmethod
    def recent(cls, count=None, ep_type=None):
        """ api call for last events"""
        filters = {}
        if count is None: count = 50
        if ep_type is not None:
            if ep_type.lower() == "ip": filters = {"type": "ip"}
            else: filters = {"type": "mac"}

        # get ep with most recent events
        recent_events = Rest.read.__func__(cls, current_app.mongo.db.ep_history,
            filter_attr = filters,
            rule_dn = "/ept/",
            projection = {"events":{"$slice":1}},
            limit = count,
            sort = "events.0.ts",
            sort_descend = True
        )

        # remap just timestamp for last move from recent_events results
        result = {
            "recent_events": []
        }
        for r in recent_events["ep_history"]:
            le = r.pop("events", None)
            if len(le)>0: le = le[0]
            else: continue
            for x in ["addr", "fabric", "node", "type", "vnid"]:
                le[x] = r[x] if x in r else ""
            result["recent_events"].append(le)
        return result

    @classmethod
    def current_stale(cls, count=None, ep_type=None):
        """ api call for current stale endpoints 
            NOTE, this is a query against ep_history table for is_stale flag,
            not a check against ep_stale table (which, ironically, is historic
            only) 
        """
        filters = {}
        if count is None: count = 50
        if ep_type is not None:
            if ep_type.lower() == "ip": filters = {"type": "ip"}
            else: filters = {"type": "mac"}

        # get ep that are currently stale
        filters["is_stale"] = True
        current_events=Rest.read.__func__(cls, current_app.mongo.db.ep_history,
            filter_attr = filters,
            rule_dn = "/ept/",
            projection = {"events":{"$slice":1}},
            limit = count,
            sort = "events.0.ts",
            sort_descend = True
        )

        result = {
            "current_stale": []
        }
        # remap just timestamp for last event 
        for r in current_events["ep_history"]:
            le = r.pop("events", None)
            if le is not None and len(le)>0 and "ts" in le[0]:
                r["ts"] = le[0]["ts"]
            else:
                r["ts"] = 0
            result["current_stale"].append(r)
        return result

    @classmethod
    def current_offsubnet(cls, count=None, ep_type=None):
        """ api call for current offsubnet endpoints 
            NOTE, this is a query against ep_history table for is_offsubnet flag,
            not a check against ep_offsubnet table (which, ironically, is historic
            only) 
        """
        filters = {}
        if count is None: count = 50

        # get ep that are currently offsubnet
        filters["is_offsubnet"] = True
        current_events=Rest.read.__func__(cls, current_app.mongo.db.ep_history,
            filter_attr = filters,
            rule_dn = "/ept/",
            projection = {"events":{"$slice":1}},
            limit = count,
            sort = "events.0.ts",
            sort_descend = True
        )

        result = {
            "current_offsubnet": []
        }
        # remap just timestamp for last event 
        for r in current_events["ep_history"]:
            le = r.pop("events", None)
            if le is not None and len(le)>0 and "ts" in le[0]:
                r["ts"] = le[0]["ts"]
            else:
                r["ts"] = 0
            result["current_offsubnet"].append(r)
        return result

    @classmethod
    def update(cls):
        """ block update """
        abort(400, "cannot update ep_history")

    @classmethod
    def delete(cls, fabric, vnid, addr):
        """ delete all history including moves and stale events for an endpoint
            in the fabric
        """
        # perform delete operation
        db_key = {"fabric": fabric, "vnid": vnid, "addr": addr}
        r1 = current_app.mongo.db.ep_history.delete_many(db_key)
        current_app.mongo.db.ep_moves.delete_many(db_key)
        current_app.mongo.db.ep_stale.delete_many(db_key)
        current_app.mongo.db.ep_offsubnet.delete_many(db_key)
        if r1.deleted_count == 0: abort(404, "endpoint not found")
        return {"success": True}

class EP_Move(Rest):
    """ EP_Move REST class """

    # module level logger
    logger = logging.getLogger(__name__)

    # meta data and type that are exposed via read with type and default values
    META = {
        "fabric": {"type":str, "default":"","read":True,"write":False},
        "addr": {"type":str, "default":"","read":True,"write":False},
        "vnid": {"type":str, "default":"","read":True,"write":False},
        "type": {"type":str, "default":"","read":True,"write":False},
        "events": {"type":list, "default":[],"read":True,"write":False},
        "count": {"type":int, "default":0,"read":True,"write":False},
    }

    def __init__(self):
        super(Rest, self).__init__()

    @classmethod
    def create(cls):
        """ block create requests (not implemented) """
        abort(400, "cannot create new ep_move")

    @classmethod
    def read(cls, fabric=None, addr=None, vnid=None, search=None, limit=None):
        """ api read call """
        # build filter based on addr/vnid/node
        filters = {}
        if fabric is not None: filters["fabric"] = fabric
        if addr is not None: filters["addr"] = addr
        if vnid is not None: filters["vnid"] = vnid

        projection = None
        if search is not None:
            # no result returned for empty search
            if len(search) == 0:
                return {"ep_move":[]}

            # filter only on addr not already provided
            filters["addr"] = {"$regex":search, "$options": "i"}
            # search provided then don't return event
            projection = ["addr", "vnid", "type", "count", "fabric"]
            # enforce search limit
            if limit is None: limit = 50

        r = Rest.read.__func__(cls, current_app.mongo.db.ep_moves,
            rule_dn = "/ept/",
            filter_attr = filters,
            projection = projection,
            limit = limit
        )
        return r

    @classmethod
    def top(cls, count=None, ep_type=None):
        """ api call for top count  moves """
        filters = {}
        if count is None: count = 50
        if ep_type is not None:
            if ep_type.lower() == "ip": filters = {"type": "ip"}
            else: filters = {"type": "mac"}

        # get ep with top number of moves
        top_events = Rest.read.__func__(cls, current_app.mongo.db.ep_moves,
            filter_attr = filters,
            rule_dn = "/ept/",
            projection = {"events":{"$slice":1}},
            limit = count,
            sort = "count",
            sort_descend = True
        )

        result = {
            "top_events": [],
        }
        # remap just timestamp for last event 
        for r in top_events["ep_move"]:
            le = r.pop("events", None)
            if le is not None and len(le)>0 and "dst" in le[0] and \
                "ts" in le[0]["dst"]:
                r["ts"] = le[0]["dst"]["ts"]
            else:
                r["ts"] = 0
            result["top_events"].append(r)
        return result

    @classmethod
    def recent(cls, count=None, ep_type=None):
        """ api call for recent moves """
        filters = {}
        if count is None: count = 50
        if ep_type is not None:
            if ep_type.lower() == "ip": filters = {"type": "ip"}
            else: filters = {"type": "mac"}

        # get ep with most recent moves
        recent_events = Rest.read.__func__(cls, current_app.mongo.db.ep_moves,
            filter_attr = filters,
            rule_dn = "/ept/",
            projection = {"events":{"$slice":1}},
            limit = count,
            sort = "events.0.dst.ts",
            sort_descend = True
        )
        result = {
            "recent_events": []
        }
        # remap just timestamp for last event 
        for r in recent_events["ep_move"]:
            le = r.pop("events", None)
            if le is not None and len(le)>0 and "dst" in le[0] and \
                "ts" in le[0]["dst"]:
                r["ts"] = le[0]["dst"]["ts"]
            else:
                r["ts"] = 0
            result["recent_events"].append(r)

        return result

    @classmethod
    def update(cls):
        """ block update """
        abort(400, "cannot update ep_move")

    @classmethod
    def delete(cls):
        """ block delete requests (not implemented) """
        abort(400, "cannot delete ep_move")

class EP_Stale(Rest):
    """ EP_Stale REST class """

    # module level logger
    logger = logging.getLogger(__name__)

    # meta data and type that are exposed via read with type and default values
    META = {
        "fabric": {"type":str, "default":"","read":True,"write":False},
        "addr": {"type":str, "default":"","read":True,"write":False},
        "vnid": {"type":str, "default":"","read":True,"write":False},
        "type": {"type":str, "default":"","read":True,"write":False},
        "node": {"type":str, "default":"","read":True,"write":False},
        "events": {"type":list, "default":[],"read":True,"write":False},
        "count": {"type":int, "default":0,"read":True,"write":False},
    }

    def __init__(self):
        super(Rest, self).__init__()

    @classmethod
    def create(cls):
        """ block create requests (not implemented) """
        abort(400, "cannot create new ep_stale")

    @classmethod
    def read(cls, fabric=None, addr=None, vnid=None, node=None, search=None,
        limit=None):
        """ api read call """
        # build filter based on addr/vnid/node
        filters = {}
        if fabric is not None: filters["fabric"] = fabric
        if addr is not None: filters["addr"] = addr
        if vnid is not None: filters["vnid"] = vnid
        if node is not None: filters["node"] = node 

        projection = None
        if search is not None:
            # no result returned for empty search
            if len(search) == 0:
                return {"ep_stale":[]}

            # filter only on addr not already provided
            filters["addr"] = {"$regex":search, "$options": "i"}
            # search provided then don't return event
            projection = ["addr", "vnid", "node", "type", "count", "fabric"]
            # enforce search limit
            if limit is None: limit = 50

        r = Rest.read.__func__(cls, current_app.mongo.db.ep_stale,
            rule_dn = "/ept/",
            filter_attr = filters,
            projection = projection,
            limit = limit
        )
        return r

    @classmethod
    def top(cls, count=None, ep_type=None):
        """ api call for top count """
        filters = {}
        if count is None: count = 50
        if ep_type is not None:
            if ep_type.lower() == "ip": filters = {"type": "ip"}
            else: filters = {"type": "mac"}

        # get ep with top number of events
        top_events = Rest.read.__func__(cls, current_app.mongo.db.ep_stale,
            filter_attr = filters,
            rule_dn = "/ept/",
            projection = {"events":{"$slice":1}},
            limit = count,
            sort = "count",
            sort_descend = True
        )

        result = {
            "top_events": [],
        }
        # remap just timestamp for last event 
        for r in top_events["ep_stale"]:
            le = r.pop("events", None)
            if le is not None and len(le)>0 and "ts" in le[0]:
                r["ts"] = le[0]["ts"]
            else:
                r["ts"] = 0
            result["top_events"].append(r)
        return result

    @classmethod
    def recent(cls, count=None, ep_type=None):
        """ api call for recent stale """
        filters = {}
        if count is None: count = 50
        if ep_type is not None:
            if ep_type.lower() == "ip": filters = {"type": "ip"}
            else: filters = {"type": "mac"}

        # get ep with most recent events
        recent_events = Rest.read.__func__(cls, current_app.mongo.db.ep_stale,
            filter_attr = filters,
            rule_dn = "/ept/",
            projection = {"events":{"$slice":1}},
            limit = count,
            sort = "events.0.ts",
            sort_descend = True
        )

        result = {
            "recent_events": []
        }
        # remap just timestamp for last event 
        for r in recent_events["ep_stale"]:
            le = r.pop("events", None)
            if le is not None and len(le)>0 and "ts" in le[0]:
                r["ts"] = le[0]["ts"]
            else:
                r["ts"] = 0
            result["recent_events"].append(r)
        return result

    @classmethod
    def update(cls):
        """ block update """
        abort(400, "cannot update ep_stale")

    @classmethod
    def delete(cls):
        """ block delete requests to settings (not implemented) """
        abort(400, "cannot delete ep_stale")


class EP_OffSubnet(Rest):
    """ EP_OffSubnet REST class """

    # module level logger
    logger = logging.getLogger(__name__)

    # meta data and type that are exposed via read with type and default values
    META = {
        "fabric": {"type":str, "default":"","read":True,"write":False},
        "addr": {"type":str, "default":"","read":True,"write":False},
        "vnid": {"type":str, "default":"","read":True,"write":False},
        "type": {"type":str, "default":"","read":True,"write":False},
        "node": {"type":str, "default":"","read":True,"write":False},
        "events": {"type":list, "default":[],"read":True,"write":False},
        "count": {"type":int, "default":0,"read":True,"write":False},
    }

    def __init__(self):
        super(Rest, self).__init__()

    @classmethod
    def create(cls):
        """ block create requests (not implemented) """
        abort(400, "cannot create new ep_offsubnet")

    @classmethod
    def read(cls, fabric=None, addr=None, vnid=None, node=None, search=None,
        limit=None):
        """ api read call """
        # build filter based on addr/vnid/node
        filters = {}
        if fabric is not None: filters["fabric"] = fabric
        if addr is not None: filters["addr"] = addr
        if vnid is not None: filters["vnid"] = vnid
        if node is not None: filters["node"] = node 

        projection = None
        if search is not None:
            # no result returned for empty search
            if len(search) == 0:
                return {"ep_stale":[]}

            # filter only on addr not already provided
            filters["addr"] = {"$regex":search, "$options": "i"}
            # search provided then don't return event
            projection = ["addr", "vnid", "node", "type", "count", "fabric"]
            # enforce search limit
            if limit is None: limit = 50

        r = Rest.read.__func__(cls, current_app.mongo.db.ep_offsubnet,
            rule_dn = "/ept/",
            filter_attr = filters,
            projection = projection,
            limit = limit
        )
        return r

    @classmethod
    def top(cls, count=None):
        """ api call for top count """
        filters = {}
        if count is None: count = 50

        # get ep with top number of events
        top_events = Rest.read.__func__(cls, current_app.mongo.db.ep_offsubnet,
            filter_attr = filters,
            rule_dn = "/ept/",
            projection = {"events":{"$slice":1}},
            limit = count,
            sort = "count",
            sort_descend = True
        )

        result = {
            "top_events": [],
        }
        # remap just timestamp for last event 
        for r in top_events["ep_offsubnet"]:
            le = r.pop("events", None)
            if le is not None and len(le)>0 and "ts" in le[0]:
                r["ts"] = le[0]["ts"]
            else:
                r["ts"] = 0
            result["top_events"].append(r)
        return result

    @classmethod
    def recent(cls, count=None):
        """ api call for recent offsubnet"""
        filters = {}
        if count is None: count = 50

        # get ep with most recent events
        recent_events = Rest.read.__func__(cls, 
            current_app.mongo.db.ep_offsubnet,
            filter_attr = filters,
            rule_dn = "/ept/",
            projection = {"events":{"$slice":1}},
            limit = count,
            sort = "events.0.ts",
            sort_descend = True
        )

        result = {
            "recent_events": []
        }
        # remap just timestamp for last event 
        for r in recent_events["ep_offsubnet"]:
            le = r.pop("events", None)
            if le is not None and len(le)>0 and "ts" in le[0]:
                r["ts"] = le[0]["ts"]
            else:
                r["ts"] = 0
            result["recent_events"].append(r)
        return result

    @classmethod
    def update(cls):
        """ block update """
        abort(400, "cannot update ep_offsubnet")

    @classmethod
    def delete(cls):
        """ block delete requests to settings (not implemented) """
        abort(400, "cannot delete ep_offsubnet")


class EP_VNIDs(Rest):
    """ EP_VNIDs REST class """

    # module level logger
    logger = logging.getLogger(__name__)

    # meta data and type that are exposed via read with type and default values
    META = {
        "fabric": {"type":str, "default":"","read":True,"write":False},
        "vnid": {"type":str, "default":"","read":True,"write":False},
        "name": {"type":str, "default":"","read":True,"write":False},
        "pcTag": {"type":str, "default":"","read":True,"write":False},
        "encap": {"type":str, "default":"","read":True,"write":False},
    }

    def __init__(self):
        super(Rest, self).__init__()

    @classmethod
    def create(cls):
        """ block create requests (not implemented) """
        abort(400, "cannot create new ep_vnid")

    @classmethod
    def read(cls, fabric=None, vnid=None, name=None, search=None, limit=None):
        """ api read call """

        # build filter based on addr/vnid/node
        filters = {}
        if fabric is not None: filters["fabric"] = fabric
        if vnid is not None: filters["vnid"] = vnid
        if name is not None: filters["name"] = name

        projection = None
        if search is not None:
            # no result returned for empty search
            if len(search) == 0:
                return {"ep_vnids":[]}

            # filter only on name not already provided
            filters["name"] = {"$regex":search, "$options": "i"}
            # search provided then don't return event
            projection = ["fabric", "vnid", "name", "pcTag", "encap"]
            # enforce search limit
            if limit is None: limit = 50

        r = Rest.read.__func__(cls, current_app.mongo.db.ep_vnids,
            rule_dn = "/ept/",
            filter_attr = filters,
            projection = projection,
            limit = limit
        )
        return r

    @classmethod
    def update(cls):
        """ block update """
        abort(400, "cannot update ep_vnid")

    @classmethod
    def delete(cls):
        """ block delete requests to settings (not implemented) """
        abort(400, "cannot delete ep_vnid")


