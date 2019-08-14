from ... rest import Rest
from .. utils import get_class
from .. utils import get_apic_session

import copy
import logging
import time

# module level logging
logger = logging.getLogger(__name__)

class ManagedObject(Rest):
    
    logger = logger

    VALIDATE = False                # flag to force validation on rebuild
    TRUST_SUBSCRIPTION = True       # flag to indicate trusted subscriptions (or refresh required)

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "doc_enable": False,
    }

    META = {
        "dn": {
            "type": str,
            "key": True,
            "key_index": 1,
            "key_type": "path",
            "description": "object distinguished name (DN)",
        },
        "modTs": {
            "type": str,
            "description": "managed object modified timestamp if present in MIT",
        },
        "ts": {
            "type": float,
            "description": "epoch timestamp when object was added/updated within local db"
        },
    }

    @classmethod
    def append_meta(cls, meta):
        ret = copy.deepcopy(cls.META)
        for k in meta: ret[k] = meta[k]
        return ret

    @classmethod
    def append_meta_access(cls, meta_access):
        ret = copy.copy(cls.META_ACCESS)
        for k in meta_access: ret[k] = meta_access[k]
        return ret

    @classmethod
    def rebuild(cls, fabric, session=None):
        """ rebuild collection 
            requires instance of Fabric object and optional session object for queries
            return tuple (bool success, error message)
        """
        classname = cls.__name__
        logger.debug("db rebuild of '%s'", classname)
        cls.delete(_filters={"fabric":fabric.fabric})

        if session is None:
            session = get_apic_session(fabric)
            if session is None:
                errmsg = "failed to get apic session for fabric %s" % fabric.fabric
                logger.warn("MO rebuild %s", errmsg)
                return (False, errmsg)

        data = get_class(session, classname, orderBy="%s.dn" % classname, stream=True)
        if data is None:
            errmsg = "failed to get data for classname %s" % classname
            logger.warn("MO rebuild %s", errmsg)
            return (False, errmsg)

        ts = time.time()
        bulk_objects = []
        for obj in data:
            if type(obj) is dict and len(obj)>0:
                cname = obj.keys()[0]
                if "attributes" in obj[cname]:
                    attr = obj[cname]["attributes"]
                    if "dn" not in attr:
                        errmsg = "invalid %s object with no dn" % classname
                        logger.warn("MO rebuild %s: %s", errmsg, attr)
                        return (False, errmsg)
                    else:
                        db_obj = {"fabric": fabric.fabric, "ts": ts}
                        for a in cls._attributes:
                            if a in attr:
                                db_obj[a] = attr[a]
                        bulk_objects.append(cls(**db_obj))
            else:
                errmsg = "failed to get stream data from class query for %s" % classname
                logger.warn("MO rebuild %s", errmsg)
                return (False, errmsg)
        if len(bulk_objects)>0:
            cls.bulk_save(bulk_objects, skip_validation=not cls.VALIDATE)
        else:
            logger.debug("no objects of %s to insert", classname)
        return (True, "")

