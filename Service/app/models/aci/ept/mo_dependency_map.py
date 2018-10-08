"""
maintain dependency mapping to ease subscription events for APIC MOs
"""

from . mo_dependency import DependencyNode
from . ept_epg import eptEpg
from . ept_subnet import eptSubnet
from . ept_vnid import eptVnid
from . ept_vpc import eptVpc

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
# vpc objects
n_vpcRsVpcConf = DependencyNode("vpcRsVpcConf")

# build tree that this application cares about...
n_fvCtx.add_child(n_l3extRsEctx, "dn", "tDn")
n_l3extRsEctx.add_child(n_l3extOut, "parent", "dn")
n_l3extOut.add_child(n_l3extExtEncapAllocator, "dn", "parent")

# svc bd mappings (same as bd)
n_fvSvcBD.add_child(n_fvSubnet, "dn", "parent")
n_fvSvcBD.add_child(n_fvRsBd, "dn", "tDn")
n_fvSvcBD.add_child(n_vnsRsEPpInfoToBD, "dn", "tDn")
n_fvSvcBD.add_child(n_vnsRsLIfCtxToBD, "dn", "tDn")
n_fvSvcBD.add_child(n_mgmtRsMgmtBD, "dn", "tDn")

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



# dict lookup for each object into dependency tree
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
    "vpcRsVpcConf": n_vpcRsVpcConf,
}

# statically map IFC MOs to ept db objects eptVnid, eptEpg, eptSubnet
ept_map = {
    # eptVnid
    "fvCtx": {
        "db": eptVnid,
        "attributes": {
            "name": "dn",
            "vnid": "scope",
            "vrf": "scope",
            "pctag": "pcTag",
        },
    },
    "fvBD": {
        "db": eptVnid,
        "attributes": {
            "name": "dn",
            "vnid": "seg",
            "vrf": "scope",
            "pctag": "pcTag",
        },
    },
    "fvSvcBD": {
        "db": eptVnid,
        "attributes": {
            "name": "dn",
            "vnid": "seg",
            "vrf": "scope",
            "pctag": "pcTag",
        },
    },
    "l3extExtEncapAllocator": {
        "db": eptVnid,
        "attributes": {
            "name": "dn",
            "encap": "encap",
            "vnid": "extEncap",
            "vrf": "fvCtx.scope",
        },
        "regex_map": {
            "vnid": "vxlan-(?P<value>[0-9]+)",
        },
    },
    # eptEpg
    "fvAEPg": {
        "db": eptEpg,
        "attributes": {
            "name": "dn",
            "vrf": "scope",
            "pctag": "pcTag",
            "is_attr_based": "isAttrBasedEPg",
            "bd": ["fvBD.seg", "fvSvcBD.seg"],
        },
    },
    "l3extInstP": {
        "db": eptEpg,
        "attributes": {
            "name": "dn",
            "vrf": "scope",
            "pctag": "pcTag",
        },
    },
    "vnsEPpInfo": {
        "db": eptEpg,
        "attributes": {
            "name": "dn",
            "vrf": "scope",
            "pctag": "pcTag",
            "bd": ["fvBD.seg", "fvSvcBD.seg"],
        },
    },
    "mgmtInB": {
        "db": eptEpg,
        "attributes": {
            "name": "dn",
            "vrf": "scope",
            "pctag": "pcTag",
            "bd": "fvBD.seg",
        },
    },
    # eptSubnet
    "fvSubnet": {
        "db": eptSubnet,
        "attributes": {
            "name": "dn", 
            "ip": "ip",
            "bd": ["fvBD.seg", "fvSvcBD.seg"],
        },
    },
    "fvIpAttr": {
        "db": eptSubnet,
        "attributes": {
            "name": "dn",
            "ip": "ip",
            "bd": ["fvBD.seg", "fvSvcBD.seg"],
        },
    },
    # vpc
    "vpcRsVpcConf": {
        "db": eptVpc,
        "attributes": {
            "node": "dn",
            "name": "dn",
            "intf": "tSKey",
            "vpc": "parentSKey",
        },
        "regex_map": {
            "node": "topology/pod-[0-9]+/node-(?P<value>[0-9]+)/",
        },
    },
}

# add ept_map info to DependencyNode object
for classname in ept_map:
    if classname in dependency_map:
        dependency_map[classname].set_ept_map(**ept_map[classname])

