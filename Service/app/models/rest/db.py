
from . import Role
from . import Universe
from . import registered_classes
from ..utils import get_db
from .settings import Settings
from .user import User

from pymongo import ASCENDING
from werkzeug.exceptions import BadRequest

import logging
import uuid

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
    if len(collections)>0 and ("user" in collections and "settings" in collections):
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
                indexes.append((a,ASCENDING))
            indexes = [(a, ASCENDING) for a in c._dn_attributes]
        elif type(c._access["db_index"]) is list:
            indexes = [(a, ASCENDING) for a in c._access["db_index"]]
        else:
            raise Exception("invalid db_index for %s: %s" % (c._classname, c._access["db_index"]))
        if len(indexes)>0:
            logger.debug("creating indexes for %s: %s",c._classname,indexes)
            db[c._classname].create_index(indexes, unique=unique)

        # support second search-only (non-unique) index for objects
        if type(c._access["db_index2"]) is list and len(c._access["db_index2"])>0:
            index2 = [(a, ASCENDING) for a in c._access["db_index2"]]
            logger.debug("creating secondary index for %s: %s", c._classname, index2)
            db[c._classname].create_index(index2, unique=False)


        if sharding and c._access["db_shard_enable"]:
            shard_indexes = {}
            if c._access["db_shard_index"] is not None:
                for a in c._access["db_shard_index"]: shard_indexes[a] = 1
            else:
                for (a,d) in indexes: shard_indexes[a] = 1
            logger.debug("creating shard index for %s: %s", c._classname, shard_indexes)
            sh.command("shardCollection", "%s.%s" % (db.name, c._classname), key=shard_indexes)

    # if uni is enabled then required before any other object is created
    uni = Universe.load()
    uni.save()
        
    # insert settings with user provided values 
    lpass = "%s"%uuid.uuid4()
    s = Settings(app_name=app_name, lpass = lpass)
    try: s.save()
    except BadRequest as e:
        logger.error("failed to create settings: %s. Using all defaults"%e)
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

    #successful setup
    return True



