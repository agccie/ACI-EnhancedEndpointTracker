import logging
import re
import time
import uuid

from pymongo import ASCENDING
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from werkzeug.exceptions import BadRequest

from . import Role
from . import Universe
from . import registered_classes
from .settings import Settings
from .user import User
from ..utils import get_db

# module level logging
logger = logging.getLogger(__name__)


def db_exists():
    """ check if database exists by verifying presents of any of the following
        collections:
            users 
            settings
    """
    logger.debug("checking if db exists")
    collections = get_db().collection_names()
    logger.debug("current collections: %s" % collections)
    if len(collections) > 0 and ("user" in collections and "settings" in collections):
        return True
    return False


def db_setup(app_name="App", username="admin", password="cisco", sharding=False, force=False):
    """ delete any existing database and setup all tables for new database 
        returns boolean success
    """
    logger.debug("setting up new database (force:%r)", force)

    if not force and db_exists():
        logger.debug("db already exists")
        return True

    db = get_db()
    sh = db.client.admin
    if sharding:
        logger.debug("enabling sharding for db %s", db.name)
        sh.command("enableSharding", db.name)

    # get all objects registred to rest API, drop db and create with 
    # proper keys
    for classname in registered_classes:
        c = registered_classes[classname]
        # drop existing collection
        logger.debug("dropping collection %s" % c._classname)
        db[c._classname].drop()
        # create indexes for searching and unique keys ordered based on key order
        # indexes are unique only if expose_id is disabled
        indexes = []
        unique = not c._access["expose_id"]
        if c._access["db_index_unique"] is not None and type(c._access["db_index_unique"]) is bool:
            unique = c._access["db_index_unique"]
        if c._access["db_index"] is None:
            # auto created index based on ordered keys
            for a in c._dn_attributes:
                indexes.append((a, ASCENDING))
            indexes = [(a, ASCENDING) for a in c._dn_attributes]
        elif type(c._access["db_index"]) is list:
            indexes = [(a, ASCENDING) for a in c._access["db_index"]]
        else:
            raise Exception("invalid db_index for %s: %s" % (c._classname, c._access["db_index"]))
        if len(indexes) > 0:
            logger.debug("creating indexes for %s: %s", c._classname, indexes)
            db[c._classname].create_index(indexes, unique=unique)

        # support second search-only (non-unique) index for objects
        if type(c._access["db_index2"]) is list and len(c._access["db_index2"]) > 0:
            index2 = [(a, ASCENDING) for a in c._access["db_index2"]]
            logger.debug("creating secondary index for %s: %s", c._classname, index2)
            db[c._classname].create_index(index2, unique=False)

        if sharding and c._access["db_shard_enable"]:
            shard_indexes = {}
            if c._access["db_shard_index"] is not None:
                for a in c._access["db_shard_index"]:
                    shard_indexes[a] = 1
            else:
                for (a, d) in indexes:
                    shard_indexes[a] = 1
            logger.debug("creating shard index for %s: %s", c._classname, shard_indexes)
            sh.command("shardCollection", "%s.%s" % (db.name, c._classname), key=shard_indexes)

    # if uni is enabled then required before any other object is created
    uni = Universe.load()
    uni.save()

    # insert settings with user provided values 
    lpass = "%s" % uuid.uuid4()
    s = Settings(app_name=app_name, lpass=lpass)
    try:
        s.save()
    except BadRequest as e:
        logger.error("failed to create settings: %s. Using all defaults" % e)
        s = Settings(lpass=lpass)
        s.save()

    # create admin user with provided password and local user
    u = User(username="local", password=lpass, role=Role.FULL_ADMIN)
    if not u.save():
        logger.error("failed to create local user")
        return False
    if username == "local":
        logger.error("username 'local' is reserved, use a different default username")
        return False
    u = User(username=username, password=password, role=Role.FULL_ADMIN)
    if not u.save():
        logger.error("failed to create username: %s" % args.username)
        return False

    # successful setup
    return True


def db_add_shard(rs, timeout=60):
    """ add a shard replica set to current db
        return bool success
    """
    logger.debug("addShard replica set %s", rs)
    db = get_db()
    sh = db.client.admin

    # wait until db (mongos) is ready
    def db_alive():
        try:
            db.collection_names()
            logger.debug("successfully connected to db")
            return True
        except Exception as e:
            logger.debug("failed to connect to db: %s", e)

    ts = time.time()
    while True:
        if not db_alive():
            if ts + timeout < time.time():
                logger.warn("failed to connect to db within timeout %s", timeout)
                return False
        else:
            break
    # add the shard, even if it is already present which is a no-op
    try:
        logger.debug("adding shard: %s", rs)
        sh.command("addShard", rs)
        return True
    except OperationFailure as op_status:
        logger.warn("failed to add shard (%s): %s", op_status.code, op_status.details)
    return False


def db_init_replica_set(rs, configsvr=False, primary=True, timeout=60, retry_interval=5,
                        socketTimeoutMS=5000, connectTimeoutMS=5000, serverSelectionTimeoutMS=5000):
    """ receive a mongo replica set connection string and perform replica set initialization
        rs string must be in the standard mongo replica set form:
            <replica_set_name>/<device1_hostname:device1_port>,<device2>...,<deviceN>

        kwargs:
            configsvr           (bool) set to true if this replica set for configsvr
            primary             (bool) force device 0 to primary by setting priority to 2 and 
                                defaulting all other devices within replica set to default of 1
            timeout             (int) time in seconds to wait for other members in replica set to 
                                become available.
            retry_interval      (int) time in seconds between initialization attempts if a node 
                                within the replica set is unavailable
            PyMongo options
            http://api.mongodb.com/python/current/api/pymongo/mongo_client.html
            socketTimeoutMS     
            connectTimeoutMS   
            serverSelectionTimeoutMS

        This func will attempt to connect to the first device within the replica set to perform the
        initialization.  If unable to connected after provided timeout, then abort the operation.
        For each replica set, the following is performed to initialize it:
            1) check rs.status() to see if replica set already initialized
                "ok": 0, "code" : 94, not yet initialized 
                "ok": 1, initiated (even if all other replicas are down)
            2) if not initialized execute initialization command
                "ok": 0, "code": 74, other nodes in replica set not ready (need to retry)
                "ok": 0, "code": 93, invalid replica set config (will always fail)
                "ok": 1, success

        return boolean success
    """
    # validate replica-set string
    r1 = re.search("^(?P<rs>[^/]+)/(?P<devices>.{2,})$", rs)
    if r1 is None:
        logger.error("unable to parse replica set string: %s", rs)
        return False
    logger.debug("initiate replica set for %s", rs)
    # build initiate command
    config = {"_id": r1.group("rs"), "configsvr": configsvr, "members": []}
    devices = r1.group("devices").split(",")
    for i, d in enumerate(devices):
        m = {"_id": i, "host": d}
        if primary and i == 0:
            m["priority"] = 2
        config["members"].append(m)

    # try to connect to device 0
    uri = "mongodb://%s" % devices[0]
    client = MongoClient(uri, socketTimeoutMS=socketTimeoutMS, connectTimeoutMS=connectTimeoutMS,
                         serverSelectionTimeoutMS=serverSelectionTimeoutMS)
    try:
        ret = client.admin.command("replSetGetStatus")
        logger.debug("replica set already initialized")
        return True
    except OperationFailure as op_status:
        if op_status.code == 94:
            logger.debug("replica set not yet initialized")
            # try to initiate replica set with retry on error code 93
            ts = time.time()
            while ts + timeout > time.time():
                try:
                    ret = client.admin.command("replSetInitiate", config)
                    logger.debug("replica set initialization success: %s", config)
                    return True
                except OperationFailure as op:
                    logger.debug("initiate operation failure (%s): %s", op.code, op.details)
                    if op.code == 74:
                        logger.debug("one or more nodes in replica set not yet available")
                    else:
                        logger.warn("failed to initialize replica set")
                        return False
                logger.debug("retry replica set initiate in %s seconds", retry_interval)
                time.sleep(retry_interval)
            logger.warn("failed to initiate replica set after %s seconds", timeout)
        else:
            logger.warn("failed to determine current replica state status: (%s) %s", op_status.code,
                        op_status.details)
    return False
