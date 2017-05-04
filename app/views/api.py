
from flask import current_app, Blueprint, render_template, abort, request
api = Blueprint("api", __name__)

from . import doc
from . import base
from . import auth
from . import admin
from . import ept

#### base

@api.route("/proxy", methods=["GET","POST"])
@api.route("/proxy.json", methods=["GET","POST"])
@doc.autodoc.doc()
def base_aci_app_proxy(): return base.aci_app_proxy()
base_aci_app_proxy.__doc__ = base.aci_app_proxy.__doc__

#### auth

@api.route("/logout", methods=["GET", "POST"])
@doc.autodoc.doc()
def auth_logout(): return auth.api_logout()
auth_logout.__doc__ = auth.api_logout.__doc__

@api.route("/login", methods=["POST"])
@doc.autodoc.doc()
def auth_login(): return auth.api_login()
auth_login.__doc__ = auth.api_login.__doc__

#### admin 

@api.route("/config", methods=["GET"])
@doc.autodoc.doc()
def admin_read_config(): return admin.read_config()
admin_read_config.__doc__ = admin.read_config.__doc__

@api.route("/config", methods=["POST"])
@doc.autodoc.doc()
def admin_update_config(): return admin.update_config()
admin_update_config.__doc__ = admin.update_config.__doc__

@api.route("/users", methods=["POST"])
@doc.autodoc.doc()
def admin_create_user(): return admin.create_user()
admin_create_user.__doc__ = admin.create_user.__doc__

@api.route("/users", methods=["GET"])
@doc.autodoc.doc()
def admin_read_users(): return admin.read_users()
admin_read_users.__doc__ = admin.read_users.__doc__

@api.route("/users/<string:username>", methods=["GET"])
@doc.autodoc.doc()
def admin_read_user(username): return admin.read_user(username)
admin_read_users.__doc__ = admin.read_users.__doc__

@api.route("/users/<string:username>/pwreset", methods=["GET"])
@doc.autodoc.doc()
def admin_read_user_pwreset(username): return admin.read_user_pwreset(username)
admin_read_user_pwreset.__doc__ = admin.read_user_pwreset.__doc__

@api.route("/users/<string:username>", methods=["POST"])
@doc.autodoc.doc()
def admin_update_user(username): return admin.update_user(username)
admin_update_user.__doc__ = admin.update_user.__doc__

@api.route("/users/pwreset", methods=["POST"])
@doc.autodoc.doc()
def admin_update_user_pwreset(): return admin.update_user_pwreset()
admin_update_user_pwreset.__doc__ = admin.update_user_pwreset.__doc__

@api.route("/users/<string:username>", methods=["DELETE"])
@doc.autodoc.doc()
def admin_delete_user(username): return admin.delete_user(username)
admin_delete_user.__doc__ = admin.delete_user.__doc__

@api.route("/rules", methods=["POST"])
@doc.autodoc.doc()
def admin_create_rule(): return admin.create_rule()
admin_create_rule.__doc__ = admin.create_rule.__doc__

@api.route("/rules", methods=["GET"])
@doc.autodoc.doc()
def admin_read_rules(): return admin.read_rules()
admin_read_rules.__doc__ = admin.read_rules.__doc__

@api.route("/rules/<path:dn>", methods=["GET"])
@doc.autodoc.doc()
def admin_read_rule(dn): return admin.read_rule("/"+dn)
admin_read_rule.__doc__ = admin.read_rule.__doc__

@api.route("/rules/<path:dn>", methods=["POST"])
@doc.autodoc.doc()
def admin_update_rule(dn): return admin.update_rule("/"+dn)
admin_update_rule.__doc__ = admin.update_rule.__doc__

@api.route("/rules/incr", methods=["POST"])
@doc.autodoc.doc()
def admin_update_rule_incr(): return admin.update_rule_incr()
admin_update_rule_incr.__doc__ = admin.update_rule_incr.__doc__

@api.route("/rules/<path:dn>", methods=["DELETE"])
@doc.autodoc.doc()
def admin_delete_rule(dn): return admin.delete_rule("/"+dn)
admin_delete_rule.__doc__ = admin.delete_rule.__doc__

@api.route("/groups", methods=["POST"])
@doc.autodoc.doc()
def admin_create_group(): return admin.create_group()
admin_create_group.__doc__ = admin.create_group.__doc__

@api.route("/groups", methods=["GET"])
@doc.autodoc.doc()
def admin_read_groups(): return admin.read_groups()
admin_read_groups.__doc__ = admin.read_groups.__doc__

@api.route("/groups/<string:group>", methods=["GET"])
@doc.autodoc.doc()
def admin_read_group(group): return admin.read_group(group)
admin_read_group.__doc__ = admin.read_group.__doc__

@api.route("/groups/<string:group>", methods=["POST"])
@doc.autodoc.doc()
def admin_update_group(group): return admin.update_group(group)
admin_update_group.__doc__ = admin.update_group.__doc__

@api.route("/groups/incr", methods=["POST"])
@doc.autodoc.doc()
def admin_update_group_incr(): return admin.update_group_incr()
admin_update_group_incr.__doc__ = admin.update_group_incr.__doc__

@api.route("/groups/<string:group>", methods=["DELETE"])
@doc.autodoc.doc()
def admin_delete_group(group): return admin.delete_group(group)
admin_delete_group.__doc__ = admin.delete_group.__doc__

#### ept

@api.route("/ept/restart/<string:fabric>", methods=["POST"])
@doc.autodoc.doc()
def ept_restart(fabric):  return ept.ept_restart(fabric)
ept_restart.__doc__ = ept.ept_restart.__doc__

@api.route("/ept/stop/<string:fabric>", methods=["POST"])
@doc.autodoc.doc()
def ept_stop(fabric):  return ept.ept_stop(fabric)
ept_stop.__doc__ = ept.ept_stop.__doc__

@api.route("/ept/clear/<string:fabric>/<int:vnid>/<string:addr>",
    methods=["POST"])
@doc.autodoc.doc()
def ept_clear_endpoint(fabric, vnid, addr): 
    return ept.ept_clear_endpoint(fabric, "%s"%vnid, addr)
ept_clear_endpoint.__doc__ = ept.ept_clear_endpoint.__doc__

@api.route("/ept/app_started", methods=["GET"])
@doc.autodoc.doc()
def ept_app_started(): return ept.app_started()
ept_app_started.__doc__ = ept.app_started.__doc__

@api.route("/ept/settings", methods=["POST"])
@doc.autodoc.doc()
def ept_create_setting(): return ept.create_setting()
ept_create_setting.__doc__ = ept.create_setting.__doc__

@api.route("/ept/settings", methods=["GET"])
@doc.autodoc.doc()
def ept_read_settings(): return ept.read_settings()
ept_read_settings.__doc__ = ept.read_settings.__doc__

@api.route("/ept/settings/<string:fabric>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_setting(fabric): return ept.read_setting(fabric)
ept_read_setting.__doc__ = ept.read_setting.__doc__

@api.route("/ept/settings/<string:fabric>", methods=["POST"])
@doc.autodoc.doc()
def ept_update_settings(fabric): return ept.update_settings(fabric)
ept_update_settings.__doc__ = ept.update_settings.__doc__

@api.route("/ept/settings/<string:fabric>", methods=["DELETE"])
@doc.autodoc.doc()
def ept_delete_settings(fabric): return ept.delete_settings(fabric)
ept_delete_settings.__doc__ = ept.delete_settings.__doc__

@api.route("/ept/settings/<string:fabric>/test", methods=["POST"])
@doc.autodoc.doc()
def ept_check_fabric_credentials(fabric): 
    return ept.check_fabric_credentials(fabric)
ept_check_fabric_credentials.__doc__ = ept.check_fabric_credentials.__doc__

@api.route("/ept/processes", methods=["GET"])
@doc.autodoc.doc()
def ept_read_processes_count(): return ept.read_processes_count()
ept_read_processes_count.__doc__ = ept.read_processes_count.__doc__

@api.route("/ept/nodes", methods=["GET"])
@doc.autodoc.doc()
def ept_read_nodes(): return ept.read_nodes()
ept_read_nodes.__doc__ = ept.read_nodes.__doc__

@api.route("/ept/tunnels", methods=["GET"])
@doc.autodoc.doc()
def ept_read_tunnels(): return ept.read_tunnels()
ept_read_tunnels.__doc__ = ept.read_tunnels.__doc__

@api.route("/ept/history/<string:fabric>/<int:node>/<int:vnid>/<string:addr>",
    methods=["GET"])
@doc.autodoc.doc()
def ept_read_history(fabric,node,vnid,addr): 
    return ept.read_history(fabric=fabric,node="%s"%node,vnid="%s"%vnid,
        addr=addr)
ept_read_history.__doc__ = ept.read_history.__doc__

@api.route("/ept/history/<string:fabric>/<int:node>/<int:vnid>",methods=["GET"])
@doc.autodoc.doc()
def ept_read_history_node_vnid(fabric,node,vnid): 
    return ept.read_history(fabric=fabric,node="%s"%node,vnid="%s"%vnid)
ept_read_history_node_vnid.__doc__ = ept.read_history.__doc__

@api.route("/ept/history/<string:fabric>/<int:node>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_history_node(fabric,node): 
    return ept.read_history(fabric=fabric,node="%s"%node)
ept_read_history_node.__doc__ = ept.read_history.__doc__

@api.route("/ept/history/<string:fabric>/vnid/<int:vnid>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_history_vnid(fabric,vnid): 
    return ept.read_history(fabric=fabric,vnid="%s"%vnid)
ept_read_history_vnid.__doc__ = ept.read_history.__doc__

@api.route("/ept/history/<string:fabric>/vnid/<int:vnid>/<string:addr>", 
    methods=["GET"])
@doc.autodoc.doc()
def ept_read_history_vnid_addr(fabric,vnid,addr): 
    return ept.read_history(fabric=fabric,vnid="%s"%vnid,addr=addr)
ept_read_history_vnid_addr.__doc__ = ept.read_history.__doc__

@api.route("/ept/history/search/<string:search>", 
    methods=["GET"])
@doc.autodoc.doc()
def ept_read_history_search(search): 
    return ept.read_history(search=search)
ept_read_history_search.__doc__ = ept.read_history.__doc__

@api.route("/ept/history/search", methods=["GET"])
@doc.autodoc.doc()
def ept_read_history_search_params(): 
    # search based on required argument parameter q
    search = request.args.get('q', '')
    return ept.read_history(search=search)
ept_read_history_search_params.__doc__ = ept.read_history.__doc__

@api.route("/ept/history/count", methods=["GET"])
@doc.autodoc.doc()
def ept_read_history_count(): return ept.read_history_count()
ept_read_history_count.__doc__ = ept.read_history_count.__doc__


@api.route("/ept/history/recent", methods=["GET"])
@doc.autodoc.doc()
def ept_read_history_recent(): return ept.read_history_recent()
ept_read_history_recent.__doc__ = ept.read_history_recent.__doc__

@api.route("/ept/moves/top", methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves_top(): return ept.read_moves_top()
ept_read_moves_top.__doc__ = ept.read_moves_top.__doc__

@api.route("/ept/moves/top/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves_top_count(count): return ept.read_moves_top(count=count)
ept_read_moves_top_count.__doc__ = ept.read_moves_top.__doc__

@api.route("/ept/moves/top/<string:ep_type>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves_top_type(ep_type): 
    return ept.read_moves_top(ep_type=ep_type)
ept_read_moves_top_type.__doc__ = ept.read_moves_top.__doc__

@api.route("/ept/moves/top/<string:ep_type>/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves_top_type_count(ep_type, count): 
    return ept.read_moves_top(count=count, ep_type=ep_type)
ept_read_moves_top_type_count.__doc__ = ept.read_moves_top.__doc__

@api.route("/ept/moves/recent", methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves_recent(): return ept.read_moves_recent()
ept_read_moves_recent.__doc__ = ept.read_moves_recent.__doc__

@api.route("/ept/moves/recent/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves_recent_count(count):return ept.read_moves_recent(count=count)
ept_read_moves_recent_count.__doc__ = ept.read_moves_recent.__doc__

@api.route("/ept/moves/recent/<string:ep_type>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves_recent_type(ep_type): 
    return ept.read_moves_recent(ep_type=ep_type)
ept_read_moves_recent_type.__doc__ = ept.read_moves_recent.__doc__

@api.route("/ept/moves/recent/<string:ep_type>/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves_recent_type_count(ep_type, count): 
    return ept.read_moves_recent(count=count, ep_type=ep_type)
ept_read_moves_recent_type_count.__doc__ = ept.read_moves_recent.__doc__

@api.route("/ept/moves/<string:fabric>/<int:vnid>/<string:addr>",
    methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves(fabric,vnid,addr): 
    return ept.read_moves(fabric=fabric,vnid="%s"%vnid,addr=addr)
ept_read_moves.__doc__ = ept.read_moves.__doc__

@api.route("/ept/moves/<string:fabric>/<int:vnid>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves_vnid(fabric, vnid): 
    return ept.read_moves(fabric=fabric, vnid="%s"%vnid)
ept_read_moves_vnid.__doc__ = ept.read_moves.__doc__

@api.route("/ept/moves/search/<string:search>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves_search(search): return ept.read_moves(search=search)
ept_read_moves_search.__doc__ = ept.read_moves.__doc__

@api.route("/ept/moves/search", methods=["GET"])
@doc.autodoc.doc()
def ept_read_moves_search_params(): 
    # search based on required argument parameter q
    search = request.args.get('q', '')
    return ept.read_moves(search=search)
ept_read_moves_search_params.__doc__ = ept.read_moves.__doc__

@api.route("/ept/stale/top", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_top(): return ept.read_stale_top()
ept_read_stale_top.__doc__ = ept.read_stale_top.__doc__

@api.route("/ept/stale/top/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_top_count(count): return ept.read_stale_top(count=count)
ept_read_stale_top_count.__doc__ = ept.read_stale_top.__doc__

@api.route("/ept/stale/top/<string:ep_type>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_top_type(ep_type): 
    return ept.read_stale_top(ep_type=ep_type)
ept_read_stale_top_type.__doc__ = ept.read_stale_top.__doc__

@api.route("/ept/stale/top/<string:ep_type>/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_top_type_count(ep_type, count): 
    return ept.read_stale_top(count=count, ep_type=ep_type)
ept_read_stale_top_type_count.__doc__ = ept.read_stale_top.__doc__

@api.route("/ept/stale/recent", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_recent(): return ept.read_stale_recent()
ept_read_stale_recent.__doc__ = ept.read_stale_recent.__doc__

@api.route("/ept/stale/recent/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_recent_count(count):return ept.read_stale_recent(count=count)
ept_read_stale_recent_count.__doc__ = ept.read_stale_recent.__doc__

@api.route("/ept/stale/recent/<string:ep_type>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_recent_type(ep_type): 
    return ept.read_stale_recent(ep_type=ep_type)
ept_read_stale_recent_type.__doc__ = ept.read_stale_recent.__doc__

@api.route("/ept/stale/recent/<string:ep_type>/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_recent_type_count(ep_type, count): 
    return ept.read_stale_recent(count=count, ep_type=ep_type)
ept_read_stale_recent_type_count.__doc__ = ept.read_stale_recent.__doc__

@api.route("/ept/stale/current", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_current(): return ept.read_stale_current()
ept_read_stale_current.__doc__ = ept.read_stale_current.__doc__

@api.route("/ept/stale/current/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_current_count(count):
    return ept.read_stale_current(count=count)
ept_read_stale_current_count.__doc__ = ept.read_stale_current.__doc__

@api.route("/ept/stale/current/<string:ep_type>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_current_type(ep_type): 
    return ept.read_stale_current(ep_type=ep_type)
ept_read_stale_current_type.__doc__ = ept.read_stale_current.__doc__

@api.route("/ept/stale/current/<string:ep_type>/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_current_type_count(ep_type, count): 
    return ept.read_stale_current(count=count, ep_type=ep_type)
ept_read_stale_current_type_count.__doc__ = ept.read_stale_current.__doc__

@api.route("/ept/stale/<string:fabric>/<int:node>/<int:vnid>/<string:addr>",
    methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale(fabric,node,vnid,addr): 
    return ept.read_stale(fabric=fabric,node="%s"%node,vnid="%s"%vnid,
        addr=addr)
ept_read_stale.__doc__ = ept.read_stale.__doc__

@api.route("/ept/stale/<string:fabric>/<int:node>/<int:vnid>",methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_node_vnid(fabric,node,vnid): 
    return ept.read_stale(fabric=fabric,node="%s"%node,vnid="%s"%vnid)
ept_read_stale_node_vnid.__doc__ = ept.read_stale.__doc__

@api.route("/ept/stale/<string:fabric>/<int:node>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_node(fabric,node): 
    return ept.read_stale(fabric=fabric,node="%s"%node)
ept_read_stale_node.__doc__ = ept.read_stale.__doc__

@api.route("/ept/stale/<string:fabric>/vnid/<int:vnid>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_vnid(fabric,vnid): 
    return ept.read_stale(fabric=fabric,vnid="%s"%vnid)
ept_read_stale_vnid.__doc__ = ept.read_stale.__doc__

@api.route("/ept/stale/<string:fabric>/vnid/<int:vnid>/<string:addr>", 
    methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_vnid_addr(fabric,vnid,addr): 
    return ept.read_stale(fabric=fabric,vnid="%s"%vnid,addr=addr)
ept_read_stale_vnid_addr.__doc__ = ept.read_stale.__doc__

@api.route("/ept/stale/search/<string:search>", 
    methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_search(search): 
    return ept.read_stale(search=search)
ept_read_stale_search.__doc__ = ept.read_stale.__doc__

@api.route("/ept/stale/search", methods=["GET"])
@doc.autodoc.doc()
def ept_read_stale_search_params(): 
    # search based on required argument parameter q
    search = request.args.get('q', '')
    return ept.read_stale(search=search)
ept_read_stale_search_params.__doc__ = ept.read_stale.__doc__

@api.route("/ept/offsubnet/top", methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_top(): return ept.read_offsubnet_top()
ept_read_offsubnet_top.__doc__ = ept.read_offsubnet_top.__doc__

@api.route("/ept/offsubnet/top/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_top_count(count): return ept.read_offsubnet_top(count=count)
ept_read_offsubnet_top_count.__doc__ = ept.read_offsubnet_top.__doc__

@api.route("/ept/offsubnet/recent", methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_recent(): return ept.read_offsubnet_recent()
ept_read_offsubnet_recent.__doc__ = ept.read_offsubnet_recent.__doc__

@api.route("/ept/offsubnet/recent/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_recent_count(count):return ept.read_offsubnet_recent(count=count)
ept_read_offsubnet_recent_count.__doc__ = ept.read_offsubnet_recent.__doc__

@api.route("/ept/offsubnet/current", methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_current(): return ept.read_offsubnet_current()
ept_read_offsubnet_current.__doc__ = ept.read_offsubnet_current.__doc__

@api.route("/ept/offsubnet/current/<int:count>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_current_count(count):
    return ept.read_offsubnet_current(count=count)
ept_read_offsubnet_current_count.__doc__ = ept.read_offsubnet_current.__doc__

@api.route("/ept/offsubnet/<string:fabric>/<int:node>/<int:vnid>/<string:addr>",
    methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet(fabric,node,vnid,addr): 
    return ept.read_offsubnet(fabric=fabric,node="%s"%node,vnid="%s"%vnid,
        addr=addr)
ept_read_offsubnet.__doc__ = ept.read_offsubnet.__doc__

@api.route("/ept/offsubnet/<string:fabric>/<int:node>/<int:vnid>",methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_node_vnid(fabric,node,vnid): 
    return ept.read_offsubnet(fabric=fabric,node="%s"%node,vnid="%s"%vnid)
ept_read_offsubnet_node_vnid.__doc__ = ept.read_offsubnet.__doc__

@api.route("/ept/offsubnet/<string:fabric>/<int:node>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_node(fabric,node): 
    return ept.read_offsubnet(fabric=fabric,node="%s"%node)
ept_read_offsubnet_node.__doc__ = ept.read_offsubnet.__doc__

@api.route("/ept/offsubnet/<string:fabric>/vnid/<int:vnid>", methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_vnid(fabric,vnid): 
    return ept.read_offsubnet(fabric=fabric,vnid="%s"%vnid)
ept_read_offsubnet_vnid.__doc__ = ept.read_offsubnet.__doc__

@api.route("/ept/offsubnet/<string:fabric>/vnid/<int:vnid>/<string:addr>", 
    methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_vnid_addr(fabric,vnid,addr): 
    return ept.read_offsubnet(fabric=fabric,vnid="%s"%vnid,addr=addr)
ept_read_offsubnet_vnid_addr.__doc__ = ept.read_offsubnet.__doc__

@api.route("/ept/offsubnet/search/<string:search>", 
    methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_search(search): 
    return ept.read_offsubnet(search=search)
ept_read_offsubnet_search.__doc__ = ept.read_offsubnet.__doc__

@api.route("/ept/offsubnet/search", methods=["GET"])
@doc.autodoc.doc()
def ept_read_offsubnet_search_params(): 
    # search based on required argument parameter q
    search = request.args.get('q', '')
    return ept.read_offsubnet(search=search)
ept_read_offsubnet_search_params.__doc__ = ept.read_offsubnet.__doc__


@api.route("/ept/vnids")
@doc.autodoc.doc()
def ept_read_vnids():return ept.read_vnid()
ept_read_vnids.__doc__ = ept.read_vnid.__doc__

@api.route("/ept/vnids/<string:fabric>")
@doc.autodoc.doc()
def ept_read_vnids_fabric(fabric):return ept.read_vnid(fabric=fabric)
ept_read_vnids_fabric.__doc__ = ept.read_vnid.__doc__

@api.route("/ept/vnids/<string:fabric>/<int:vnid>")
@doc.autodoc.doc()
def ept_read_vnids_vnid(fabric,vnid):
    return ept.read_vnid(fabric=fabric,vnid="%s"%vnid)
ept_read_vnids_vnid.__doc__ = ept.read_vnid.__doc__

@api.route("/ept/vnids/search", methods=["GET"])
@doc.autodoc.doc()
def ept_read_vnid_search_params(): 
    # search based on required argument parameter q
    search = request.args.get('q', '')
    return ept.read_vnid(search=search)
ept_read_vnid_search_params.__doc__ = ept.read_vnid.__doc__

@api.route("/ept/current/<string:fabric>/<int:vnid>/<string:addr>",
    methods=["GET"])
@doc.autodoc.doc()
def ept_read_current_state(fabric,vnid,addr):
    return ept.read_current_state(fabric,"%s"%vnid,addr)
ept_read_current_state.__doc__ = ept.read_current_state.__doc__

@api.route("/ept/<string:fabric>/<int:vnid>/<string:addr>",methods=["DELETE"])
@doc.autodoc.doc()
def ept_delete_endpoint(fabric,vnid,addr):
    return ept.delete_endpoint(fabric,"%s"%vnid,addr)
ept_delete_endpoint.__doc__ = ept.delete_endpoint.__doc__


