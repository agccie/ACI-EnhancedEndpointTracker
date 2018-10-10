
from .. utils import get_attributes
from . common import MO_BASE

from importlib import import_module
from werkzeug.exceptions import BadRequest

import logging
import re
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class DependencyConnector(object):
    def __init__(self, remote_node, local_attr, remote_attr):
        self.local_attr = local_attr
        self.remote_attr = remote_attr
        self.remote_node = remote_node

class DependencyNode(object):
    def __init__(self, classname):
        self.classname = classname
        self.cls_mo = getattr(import_module(".%s" % classname, MO_BASE), classname)
        self.parents = []
        self.children = []
        self.ept_db = None
        self.ept_attributes = {}
        self.ept_regex_map = {}
        self.ept_key = None

    def __repr__(self):
        return "%s, parents[%s], children[%s]" % (
            self.classname, 
            ",".join([
                "%s->%s.%s" % (c.local_attr, c.remote_node.classname, c.remote_attr) for c in self.parents
            ]),
            ",".join([
                "%s->%s.%s" % (c.local_attr, c.remote_node.classname, c.remote_attr) for c in self.children
            ]),
        )

    def add_child(self, child_node, local_attr, remote_attr): 
        self.children.append(DependencyConnector(child_node, local_attr, remote_attr))
        child_node.parents.append(DependencyConnector(self, remote_attr, local_attr))

    def set_ept_map(self, db=None, key=None, attributes=None, regex_map=None):
        """ set mapper for mo to ept objects.
                db is ept object (instance of Rest class). 

                key is db lookup key to access object.  By default will use 'name'.  Note, fabric is
                    always combined with key for object lookup

                attributes is dict mapping ept db attribute to mo db attribute.  Each attribute can
                    either be a string representing MO attribute OR can be a string in format 
                    MO.attribute where MO is a parent of the current DependencyNode and corresponding
                    attribute.  It could also be a list in scenario that multiple parents are 
                    possible and attribute could be retrieved from which ever parent is found first.
                    (statically defined in mo_dependency_map)

                regex_map is dict mapping ept db attribute to regex used to extract value. It must
                    contain a named regex group 'value' which is used to extract the value.
        """
        if db is not None and attributes is not None:
            logger.debug("initializing ept db map: %s to %s", self.classname, db._classname)
            self.ept_db = db
            self.ept_attributes = attributes
            if regex_map is None:
                self.ept_regex_map = {}
            else:
                self.ept_regex_map = regex_map
            if key is None:
                self.ept_key = "name"
            else:
                self.ept_key = key
            if self.ept_key not in self.ept_attributes:
                self.ept_attributes[self.ept_key] = self.ept_key
        else:
            logger.error("received map request without db or attributes: %s, %s", db, attributes)

    def set_ept_object(self, mo):
        # get ept object that maps to provided mo object. Note this may not currently exist in db
        # if ept_db is not defined then sets .ept to None
        if self.ept_db is None:
            setattr(mo, "ept", None)
        else:
            key = {"fabric": mo.fabric}
            key[self.ept_key] = getattr(mo, self.ept_attributes[self.ept_key])
            setattr(mo, "ept", self.ept_db.load(**key))

    def sync_ept_to_mo(self, mo, mo_parents):
        """ sync ept object to mo. Also perform sync for each child node.  Return list of all ept
            objects that were updated (created, modified, or deleted)
        """
        updates = []
        updated = False
        if hasattr(mo, "ept") and mo.ept is not None:
            ept = mo.ept
            logger.debug("sync_ept_to_mo %s to %s(%s)", ept._classname, mo._classname, mo.dn)
            # delete operation requires us to delete the ept object
            if not mo.exists():
                if ept.exists():
                    logger.debug("mo deleted, removing ept object")
                    ept.remove()
                    updates.append(ept)
                    updated = True
                else:
                    logger.debug("mo deleted and ept object does not exist, no update required")
            else:
                # force updated to true of ept object does not exist
                if not ept.exists(): updated = True
                try:
                    for a, mo_attr in self.ept_attributes.items():
                        if not hasattr(ept, a):
                            logger.warn("skipping unknown attribute %s in ept %s",a,ept._classname)
                            continue
                        # mo_attribute in one of the following formats:
                        #   attribute               - indicating string name of mo attribute
                        #   classname.attribute     - indicating parent class and parent attribute
                        #   list[ ... ]             - list of options
                        val = None
                        if type(mo_attr) is not list: mo_attr = [mo_attr]
                        for mo_a in mo_attr:
                            mo_a_split = mo_a.split(".")
                            if len(mo_a_split) == 1:
                                if hasattr(mo, mo_a_split[0]):
                                    val = getattr(mo, mo_a_split[0])
                                else:
                                    logger.warn("cannot map mo attr: %s, %s", mo._classname, mo_a)
                                break
                            elif len(mo_a_split) == 2:
                                pclass = mo_a_split[0]
                                pattr = mo_a_split[1]
                                if pclass in mo_parents:
                                    parent = mo_parents[pclass]
                                    if hasattr(parent, mo_a_split[1]):
                                        val = getattr(parent, mo_a_split[1])
                                    else:
                                        logger.warn("cannot map parent mo attr: %s", mo_a)
                                    break
                            else:
                                logger.error("unexpected/unsupported mo attribute: %s", mo_a)
                        if val is not None:
                            if a in self.ept_regex_map:
                                r1 = re.search(self.ept_regex_map[a], val)
                                if r1 is not None and "value" in r1.groupdict():
                                    val = r1.group("value")
                                else:
                                    logger.warn("failed to extract value for %s, regex: %s, from %s", 
                                        a, self.ept_regex_map[a], val)
                        else:
                            # val of none implies an unmapped attribute. This implies that a 
                            # dependency was not resolved which is common when objects are deleted.  
                            # Will force a value of '0' for all unmapped depenency
                            logger.debug("%s(%s) '%s' from %s not found, setting to 0", 
                                ept._classname, getattr(ept, self.ept_key), a, mo_attr)
                            val = 0

                        # need to cast mo value to expected value in ept object. If cast fails then
                        # corresponding save will also fail so only do comparison on successful cast
                        try:
                            val = ept.__class__.validate_attribute(a, val)
                        except BadRequest as e:
                            logger.warn("ignoring mo %s attribute %s value %s: %s", mo._classname, 
                                a, val, e)

                        if getattr(ept, a) != val:
                            logger.debug("updated %s(%s) %s from %s to %s", ept._classname, 
                                getattr(ept, self.ept_key), a, getattr(ept, a), val
                            )
                            setattr(ept, a, val)
                            updated = True
                except Exception as e:
                    logger.error("Traceback:\n%s", traceback.format_exc())
                if updated: 
                    ept.save()
                    updates.append(ept)

        # add self to parents dict and then call each child mo to perform their sync
        if hasattr(mo, "children") and len(mo.children)>0:
            # if this mo was deleted, then tree is broken and no parents are available to child 
            # dependency nodes (including self)
            if mo.exists():
                sub_parents = {}
                for classname in mo_parents: 
                    sub_parents[classname] = mo_parents[classname]
                sub_parents[self.classname] = mo
            else:
                sub_parents = {}
            for c in mo.children:
                # need to get the DependencyNode for child mo before triggering sync
                if hasattr(c, "dependency"):
                    updates+= c.dependency.sync_ept_to_mo(c, sub_parents)
                else:
                    logger.warn("cannot sync child, DependencyNode not set: %s %s",c._classname,c.dn)

        #logger.debug("sync_ept_to_mo %s(%s) returning %s updates",mo._classname,mo.dn,len(updates))
        return updates

    def sync_event(self, fabric, attr, session):
        """ receive subscription event and update mo and corresponding dependent ept objects
            return list of ept objects that were updated
            this requires 'dn', 'status', and '_ts' within provided attribute dict
        """
        logger.debug("sync event (fabric:%s), event: %s", fabric, attr)
        updates = []
        mo = self.cls_mo.load(fabric=fabric, dn=attr["dn"])
        if mo.exists() and mo.ts > attr["_ts"]:
            logger.debug("ignoring old %s event (%.3f > %.3f)", self.classname, mo.ts, attr["_ts"])
            return updates

        # perform manual refresh for non-trusting mo or non-existing mo with modify event
        if not mo.TRUST_SUBSCRIPTION or attr["status"] == "modified" and not mo.exists():
            logger.debug("mo dependency sync performing api refresh for dn: %s", attr["dn"])
            full_attr = get_attributes(session=session, dn=attr["dn"])
            if session is None:
                raise Exception("no session object provided for sync event: %s, %s" %(fabric, attr))
            if full_attr is None:
                logger.debug("failed to refresh dn, assuming deleted: %s", attr["dn"])
                attr["status"] = "deleted"
            else:
                full_attr["status"] = "created" # will always look like a created event on refresh
                full_attr["_ts"] = attr["_ts"]
                attr = full_attr

        if attr["status"] == "deleted":
            if not mo.exists():
                logger.debug("ignoring delete event for non-existing mo: %s, %s", mo._classname, 
                        attr["dn"])
                return updates
            logger.debug("delete event removing mo object(%s): %s", mo._classname, mo.dn)
            mo.remove()
        else:
            mo_update = not mo.exists()
            # sync mo to local db
            mo.ts = attr["_ts"]
            for a in attr:
                if a in mo._attributes and getattr(mo,a) != attr[a]:
                    setattr(mo, a, attr[a])
                    mo_update = True
            mo.save()

            if not mo_update:
                # no local mo update so no ept object change or child dependencies can change
                return updates

        # get ept object along with parent and child dependencies 
        self.set_ept_object(mo)
        logger.debug("getting mo dependents for %s(%s)", mo._classname, mo.dn)
        ts1 = time.time()
        parents = self.get_parent_objects(mo)
        ts2 = time.time()
        setattr(mo, "children", self.get_child_objects(mo))
        ts3 = time.time()
        logger.debug("mo timing total: %.3f, parent(%s): %.3f, child(%s): %0.3f", ts3-ts1, 
                len(parents), ts2-ts1, len(mo.children), ts3-ts2) 

        # update local ept object
        return self.sync_ept_to_mo(mo, parents)

    def get_parent_objects(self, mo):
        # return dict indexed by classname of each parent.  Note, each classname can only be one
        # object. This can only execute if self.object is set. Object will include .ept attribute
        # containing corresponding ept object (if exists and defined in ept_map)
        #
        # Note, fabric is always used as part of lookup key with connector
        mo_classname = mo.__class__.__name__
        #logger.debug("get parent objects for %s(%s)", mo_classname, mo.dn)
        ret = {}
        try:
            for connector in self.parents:
                classname = connector.remote_node.classname
                key = {
                    "fabric": mo.fabric,
                    connector.remote_attr: getattr(mo, connector.local_attr),
                }
                #logger.debug("checking for parent %s(%s=%s)", classname, connector.remote_attr,
                #                                                        key[connector.remote_attr])
                p_mo = connector.remote_node.cls_mo.find(**key)
                if len(p_mo) > 0:
                    p_mo = p_mo[0]
                    setattr(p_mo, "dependency", connector.remote_node)
                    #logger.debug("matched %s parent %s(%s)", mo_classname, classname, p_mo.dn)
                    p_ret = connector.remote_node.get_parent_objects(p_mo)
                    for k in p_ret: ret[k] = p_ret[k]
                    ret[classname] = p_mo
                    # an instance of an object will only ever have one parent, so first match is
                    # sufficient
                    break
        except Exception as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        #if len(ret)>0:
        #    logger.debug("returning %s parents: %s", mo.dn, ",".join([c for c in ret]))
        #else:
        #    logger.debug("no parents for %s", mo.dn)
        return ret

    def get_child_objects(self, mo):
        # return a list representing children where each child is a dict containing the following:
        #   [
        #       mo.object
        #           .dependency = this DependencyNode object
        #           .children = [child MOs]
        #           .ept = corresponding ept object (eptVnid, eptEpg, eptSubnet) if in ept_map
        #                   None if in map and not present in db
        #   ]
        # Note, fabric is always used as part of lookup key with connector
        mo_classname = mo.__class__.__name__
        #logger.debug("get child objects for %s(%s)", mo_classname, mo.dn)
        ret = []
        try:
            for connector in self.children:
                classname = connector.remote_node.classname
                key = {
                    "fabric": mo.fabric,
                    connector.remote_attr: getattr(mo, connector.local_attr),
                }
                #logger.debug("checking for child %s(%s=%s)", classname, connector.remote_attr,
                #                                                        key[connector.remote_attr])
                c_mo = connector.remote_node.cls_mo.find(**key)
                for c in c_mo:
                    setattr(c, "dependency", connector.remote_node)
                    connector.remote_node.set_ept_object(c)
                    #logger.debug("matched %s child %s(%s)", mo_classname, classname, c.dn)
                    setattr(c, "children", connector.remote_node.get_child_objects(c))
                    ret.append(c)
        except Exception as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        #if len(ret)>0:
        #    logger.debug("returning %s children:\n  %s", mo.dn, 
        #        "\n  ".join(["%s(%s)"%(c._classname, c.dn) for c in ret])
        #    )
        #else: 
        #    logger.debug("no children for %s", mo.dn)
        return ret


        

