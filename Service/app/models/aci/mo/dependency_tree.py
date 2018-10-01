"""
maintain dependency mapping to ease subscription events for APIC MOs
"""

class DependencyNode(object):
    def __init__(self, classname):
        self.classname = classname
        self.parents = []
        self.children = []

    def add_child(self, child_node, local_attr, remote_attr): 
        self.children.append(DependencyConnector(child_obj, local_attr, remote_attr))
        child_node.parents.append(DependencyConnector(self, remote_attr, local_attr))

class DependencyConnector(object):
    def __init__(self, remote_node, local_attr, remote_attr):
        self.local_attr = local_attr
        self.remote_attr = remote_attr
        self.remote_node = remote_node

# vnid objects
n_fvCtx = DependencyNode("fvCtx")
n_fvBD = DependencyNode("fvBD")
n_fvSvcBD = DependencyNode("fvSvcBD")
# epg objects
n_fvAEPg = DependencyNode("fvAEPg")
n_fvRsBd = DependencyNode("fvRsBd")
n_vnsEPpInfo = DependencyNode("vnsEPpInfo")
n_vnsRsEPpInfoToBD = DependencyNode("vnsRsEPpInfoToBD")
n_mgmtInB = DependencyNode("mgmtInB")
n_mgmtRsMgmtBD = DependencyNode("mgmtRsMgmtBD")
n_vnsLIfCtx = DependencyNode("vnsLIfCtx")
n_vnsRsLIfCtxToBD = DependencyNode("vnsRsLIfCtxToBD")
# l3out objects
n_l3extRsEctx = DependencyNode("l3extRsEctx")
n_l3extOut = DependencyNode("l3extOut")
n_l3extExtEncapAllocator = DependencyNode("l3extExtEncapAllocator")
n_l3extInstP = DependencyNode("l3extInstP")
# subnet objects
n_fvSubnet = DependencyNode("fvSubnet")
n_fvIpAttr = DependencyNode("fvIpAttr")

dependency_map = {
    "fvCtx": n_fvCtx,
    "fvBD": n_fvBD,
    "fvSvcBD": n_fvSvcBD,
    "fvAEPg": n_fvAEPg,
    "fvRsBd": n_fvRsBd,
    "vnsEPpInfo": n_vnsEPpInfo,
    "vnsRsEPpInfoToBD": n_vnsRsEPpInfoToBD,
    "vnsLIfCtx": n_vnsLIfCtx,
    "vnsRsLIfCtxToBD": n_vnsRsLIfCtxToBD,
    "mgmtInB": n_mgmtInB,
    "mgmtRsMgmtBD": n_mgmtRsMgmtBD,
    "l3extInstP": n_l3extInstP,
    "l3extExtEncapAllocator": n_l3extExtEncapAllocator,
    "l3extOut": n_l3extOut,
    "l3extRsEctx": n_l3extRsEctx,
    "fvSubnet": n_fvSubnet,
    "fvIpAttr": n_fvIpAttr,
}

# build tree that this application cares about...
n_fvCtx.add_child(n_l3extRsEctx, "dn", "tDn")
n_l3extRsEctx.add_child(n_l3extOut, "parent", "dn")
n_l3extOut.add_child(n_l3extExtEncapAllocator, "dn", "parent")

# svc bd mappings (same as bd)
n_fvSvcBD.add_child(n_fvSubnet, "dn", "parent")
n_fvSvcBD.add_child(n_fvRsBd, "dn", "parent")
n_fvSvcBD.add_child(n_vnsRsEPpInfoToBD, "dn", "parent")
n_fvSvcBD.add_child(n_vnsRsLIfCtxToBD, "dn", "parent")
n_fvSvcBD.add_child(n_mgmtRsMgmtBD, "dn", "parent")

# bd mappings
n_fvBD.add_child(n_fvSubnet, "dn", "parent")
n_fvBD.add_child(n_fvRsBd, "dn", "tDn")
n_fvBD.add_child(n_vnsRsEPpInfoToBD, "dn", "tDn")
n_fvBD.add_child(n_vnsRsLIfCtxToBD, "dn", "tDn")
n_fvBD.add_child(n_mgmtRsMgmtBD, "dn", "tDn")

# bd connectors to fvEPg~like objects
n_fvRsBd.add_child(n_fvAEPg, "parent", "dn")
n_vnsRsEPpInfoToBD.add_child(n_vnsEPpInfo, "parent", "dn")
n_vnsRsLIfCtxToBD.add_child(n_vnsLIfCtx, "parent", "dn")
n_mgmtRsMgmtBD.add_child(n_mgmtInB, "parent", "dn")

# fvAEPg
n_fvAEPg.add_child(n_fvSubnet, "dn", "parent")
n_fvAEPg.add_child(n_fvIpAttr, "dn", "parent")
n_vnsEPpInfo.add_child(n_fvSubnet, "dn", "parent")
n_vnsLIfCtx.add_child(n_fvSubnet, "dn", "parent")

