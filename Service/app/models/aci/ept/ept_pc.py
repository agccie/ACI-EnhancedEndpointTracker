from ...rest import Rest
from ...rest import api_callback
from ...rest import api_register
import logging
import time

# module level logging
logger = logging.getLogger(__name__)

@api_register(parent="fabric", path="ept/pc")
class eptPc(Rest):
    """ provides mapping of port-channel interface to port-channel name within a fabric """ 
    logger = logger

    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
        "db_index_unique": True,  
        "db_index": ["fabric","name"],      # fabric+name(dn) is unique (for insert/update)
        "db_index2": ["fabric", "node", "intf"],    # second index for quick lookup
    }

    META = {
        "name": {
            "type": str,
            "key": True,
            "key_sn": "pc",
            "description":"name(dn) for pcAggrIf that created this object",
        },
        "node": {
            "type": int,
            "min": 1,
            "max": 0xffffffff,
            "description": "node id in which this vpc belongs",
        },
        "intf": {
            "type": str,
            "description": "port-channel interface id",
        },
        "intf_name": {
            "type": str,
            "description": "policy name for port-channel interface",
        },
        "members": {
            "type": list,
            "subtype": str,
            "description": "list of member interfaces for this port-channel",
        },
        "ts": {
            "type": float,
            "description": "epoch timestamp the object was created or updated",
        },
    }

    @classmethod
    @api_callback("before_create")
    def before_create(cls, data):
        """ set create time on object """
        data["ts"] = time.time()
        return data

    @staticmethod
    def sync_pc_member(mo, pc=None):
        """ receive a pcRsMbrIf mo and either add or remove the interface from eptPc members list """
        # need to first check if there is a eptPc object corresponding to this mo
        #        # when sync event happens for tunnel, perform remote mapping
        logger.debug("sync pc member %s (exists: %r) for %s", mo.tSKey, mo.exists(), mo.parent)
        pc = eptPc.find(fabric=mo.fabric, name=mo.parent)
        if len(pc)>=1:
            pc = pc[0]
            mbr = mo.tSKey  
            if mo.exists():
                # if mo is not deleted and mbr is not in members list, then add it
                if mbr not in pc.members:
                    logger.debug("adding %s to members list(%s)", mbr, pc.members)
                    pc.members.append(mbr)
                    pc.save()
            else:
                # else if mo is deleted AND mbr is a member, then remove it
                if mbr in pc.members:
                    logger.debug("removing %s from members list(%s)", mbr, pc.members)
                    pc.members.remove(mbr)
                    pc.save()
        else:
            logger.debug("ignoring update for non-existing eptPc object")



