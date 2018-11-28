
// receive instance of view modal and update table to fabric view
function view_dashboard_fabric(vm){
    var self = vm;
    self.view("dashboard_fabric")
    self.view_dashboard(true)
    //build callbacks for each action
    var click_history = function(fab){
        if("fabric" in fab){
            forward("/fb-"+fab.fabric()+"/history")
        }
    }

    // refresh fabric until interesting fabric status changes to desired state or max tries are
    // exceeded
    var poll_fabric_status = function(callback, fabric_name, status, max_tries=10){
        self.refresh_fabrics(function(){
            max_tries--
            var fabric_status = ""
            var status_list = []
            if(Array.isArray(status)){ status_list = status }
            else{ status_list = [status] }
            for(var i=0; i<=self.fabrics().length; i++){
                if(self.fabrics()[i].fabric()==fabric_name){
                    fabric_status = self.fabrics()[i].status()
                    break
                }
            }
            if(status_list.includes(fabric_status) || max_tries <= 0 ){
                return callback()
            }
            if(max_tries > 0){
                setTimeout(function(){ 
                    poll_fabric_status(callback, fabric_name, status, max_tries) 
                }, 1000);
            }
        }, fabric_name)
    }

    // start fabric monitor
    var start_fabric = function(fab){
        if("fabric" in fab){
            var url="/api/uni/fb-"+fab.fabric()+"/start"
            self.table.isLoading(true)
            json_post(url, {}, function(data){
                poll_fabric_status(function(){
                        self.table.isLoading(false)
                        self.view_dashboard_fabric_refresh()
                    }, 
                    fab.fabric(), ["running"])
            })
        }
    }
    // stop fabric monitor
    var stop_fabric = function(fab){
        if("fabric" in fab){
            var url="/api/uni/fb-"+fab.fabric()+"/stop"
            self.table.isLoading(true)
            json_post(url, {}, function(data){
                poll_fabric_status(function(){
                        self.table.isLoading(false)
                        self.view_dashboard_fabric_refresh()
                    }, 
                    fab.fabric(), "stopped")
            })
        }
    }

    // forward to edit fabric settings
    var edit_fabric = function(fab){
        if("fabric" in fab){
            forward("/fb-"+fab.fabric()+"/settings")
        }
    }
    var headers = [
        {"title":"Name", "name":"fabric", "sorted":true, "sort_direction":"asc"},
        {"title":"Status", "name": "status_str"},
        {"title": "MACs", "name":"count_mac"},
        {"title": "IPv4", "name":"count_ipv4"},
        {"title": "IPv6", "name":"count_ipv6"},
        {"title": "Control", "name":"control", "sortable":false, "control":[
            new gCtrl({"tip":"Start", "status":"success", "icon":"icon-right-arrow-contained",
                        "disabled":!self.admin_role(),
                        "click": start_fabric
                    }),
            new gCtrl({"tip":"Stop", "status":"negative", "icon":"icon-stop",
                        "disabled":!self.admin_role(),
                        "click": stop_fabric
                    }),
            new gCtrl({"tip":"Edit", "status":"gray-ghost", "icon":"icon-tools",
                        "disabled":!self.admin_role(),
                        "click": edit_fabric
                    }),
            new gCtrl({"tip":"History", "status":"secondary", "icon":"icon-chevron-right",
                        "click":click_history
                    })
        ]}
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
    })
    self.table.buttons([
        new gCtrl({"tip":"Add Fabric", "status":"primary", "icon":"icon-add",
                        "disabled":!self.admin_role(),
                        "visible": !self.app_mode(),
                        "click": function(){showModalForm()}
        })
    ])


    //get all fabrics and perform a refresh on each
    self.view_dashboard_fabric_refresh = function(){
        self.table.isLoading(true)
        self.refresh_fabrics(function(){
            //perform a refresh of each fabric and add object to table
            var rows = []
            self.fabrics().forEach(function(elem){
                rows.push(new gRow(elem))
            })
            self.table.rows(rows)
            self.table.isLoading(false)
        })
    }
    //update table refresh function
    self.table.custom_refresh = self.view_dashboard_fabric_refresh
    self.view_dashboard_fabric_refresh()
}

// view events for fabric
function view_dashboard_fabric_events(vm, args){
    var self = vm;
    self.view("dashboard_fabric_events")
    self.view_dashboard(true)
    self.current_fabric_name(args[0])
    self.table.back_enabled(true)
    var headers = [
        {"title": "Time", "name":"ts_str", "sorted":true, "sort_direction":"desc"},
        {"title": "Status", "name":"status"},
        {"title": "Description", "name":"description"}
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
    })
    // get fabric object for current view fabric from self.fabrics
    var update_rows = function(){
        var rows = []
        if(!self.current_fabric_not_found()){
            self.current_fabric.events().forEach(function(elem){
                rows.push(new gRow(elem))
            })
        }else{
            self.table.no_data_message("fabric '"+self.current_fabric_name()+"' not found")
        }
        self.table.title(self.current_fabric_name())
        self.table.rows(rows)
        self.table.result_count(self.current_fabric.event_count())
        self.table.result_count_wrapped(rows.length)
    }

    self.view_dashboard_fabric_events_refresh = function(){
        self.table.isLoading(true)
        //perform refresh for single fabric
        self.refresh_fabrics(function(){
            self.table.isLoading(false)
            update_rows()
        }, fab=self.current_fabric_name())
    }
    //update table refresh function
    self.table.custom_refresh = self.view_dashboard_fabric_events_refresh
    if(self.current_fabric.fabric()!=self.current_fabric_name()){
        self.view_dashboard_fabric_events_refresh()
    }else{
        update_rows()
    }
}

// view edit options for fabric
function view_dashboard_fabric_settings(vm, args){
    var self = vm;
    self.view("dashboard_fabric_settings")
    self.current_fabric_name(args[0])
    self.view_edit_fabric(true)
    self.table.display_no_data(false)
    self.table.refresh_enabled(false)

    var tab = "connectivity"
    if(args.length>1){
        switch(args[1]){
            case "connectivity": tab="connectivity"; break;
            case "notifications": tab="notifications"; break;
            case "remediate": tab="remediate"; break;
            case "advanced": tab="advanced"; break;
        }
    }
    self.edit_fabric_tab(tab)
    if(self.current_fabric_name()!=self.current_fabric.fabric()){
        self.fabric_isLoading(true)
        self.refresh_fabrics(function(){
                self.fabric_isLoading(false)
            }, 
            self.current_fabric_name()
        )
    }
}

// view eptEndpoint events
function view_dashboard_endpoints(vm){
    var self = vm;
    self.view("dashboard_endpoints")
    self.view_dashboard(true)
    self.table.url("/api/ept/endpoint")
    var headers = [
        {"title": "Fabric", "name":"fabric"},
        {"title": "State", "name":"state", "sortable": false},
        {"title": "Type", "name": "type"},
        {"title": "Address", "name":"addr", "sorted":true, "sort_direction":"asc"},
        {"title": "VRF/BD", "name":"vnid_name" , "sort_name":"first_learn.vnid_name"}, 
        {"title": "EPG", "name":"epg_name", "sort_name":"events.0.epg_name"}
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
    })
    self.dashboard_endpoint_active_toggles = ko.observableArray([])
    //set url filters based on active_toggles
    self.dashboard_endpoint_set_filters = function(){
        if(self.dashboard_endpoint_active_toggles().length==0){
            self.table.url_params([])
        } else if(self.dashboard_endpoint_active_toggles().length==1){
            self.table.url_params(["filter="+self.dashboard_endpoint_active_toggles()[0]])
        } else{
            self.table.url_params(["filter=and("+self.dashboard_endpoint_active_toggles().join(",")+")"])
        }
    }
    var handle_toggles = function(label, checked){
        var flt = ""
        if(label == "Active"){ flt = "or(eq(\"events.0.status\",\"created\"),eq(\"events.0.status\",\"modified\"))" }
        else if(label == "OffSubnet"){ flt = "eq(\"is_offsubnet\",true)" }
        else if(label == "Stale"){ flt = "eq(\"is_stale\",true)" }
        else if(label == "Rapid"){ flt = "eq(\"is_rapid\",true)" }
        else{
            console.log("ignoring unexpected label: "+label)
            return
        }
        // if checked, then update has only occurred if flt not current in active_toggles
        if(self.dashboard_endpoint_active_toggles().includes(flt)){
            if(!checked){
                //already present but no longer checked, need to remove from filter and refresh
                var new_toggles = []
                self.dashboard_endpoint_active_toggles().forEach(function(elem){
                    if(elem!=flt){ new_toggles.push(elem) }
                })
                self.dashboard_endpoint_active_toggles(new_toggles)
                self.dashboard_endpoint_set_filters()
                self.table.refresh_data()
            }
        } else {
            if(checked){
                //new toggle to add to active toggle list
                self.dashboard_endpoint_active_toggles.push(flt)
                self.dashboard_endpoint_set_filters()
                self.table.refresh_data()
            }
        }
    }
    var toggles = [
        {"label": "Active", "callback": handle_toggles},
        {"label": "OffSubnet", "callback": handle_toggles},
        {"label": "Stale", "callback": handle_toggles},
        {"label": "Rapid", "callback": handle_toggles }
    ]
    toggles.forEach(function(t){
        self.table.toggles.push(new gToggle(t))
    })
    self.table.refresh_handler = function(api_data){
        var data=[]
        api_data.objects.forEach(function(elem){
            if("ept.endpoint" in elem){
                var obj = new eptEndpoint()
                obj.fromJS(elem["ept.endpoint"])
                data.push(obj)
            }
        })
        return data
    }
    self.table.refresh_data()
}

// view eptMove events
function view_dashboard_moves(vm){
    var self = vm;
    self.view("dashboard_moves")
    self.view_dashboard(true)
    self.table.url("/api/ept/move")
    var headers = [
        {"title": "Time", "name":"ts_str", "sort_name":"events.0.dst.ts"},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Type", "name":"type"},
        {"title": "Address", "name":"addr"},
        {"title": "Event Count", "name":"count", "sorted":true},
        {"title": "VRF/BD", "name":"vnid_name", "sort_name":"events.0.dst.vnid_name"} 
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
    })
    self.table.refresh_handler = function(api_data){
        var data=[]
        api_data.objects.forEach(function(elem){
            if("ept.move" in elem){
                var obj = new eptMove()
                obj.fromJS(elem["ept.move"])
                data.push(obj)
            }
        })
        return data
    }
    self.table.refresh_data()
}

// view eptOffsubnet events
function view_dashboard_offsubnet(vm){
    var self = vm;
    self.view("dashboard_offsubnet")
    self.view_dashboard(true)
    self.historical_tab(true)
    self.table.url("/api/ept/offsubnet")
    var headers = [
        {"title": "Time", "name":"ts_str", "sort_name":"events.0.ts", "sorted":true},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Type", "name":"type"},
        {"title": "Address", "name":"addr"},
        {"title": "Node", "name":"node"},
        {"title": "Event Count", "name":"count"},
        {"title": "VRF/BD", "name":"vnid_name", "sort_name":"events.0.vnid_name"} 
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
    })

    self.table.refresh_handler = function(api_data){
        var data=[]
        api_data.objects.forEach(function(elem){
            if("ept.offsubnet" in elem){
                var obj = new eptOffsubnet()
                obj.fromJS(elem["ept.offsubnet"])
                data.push(obj)
            }
        })
        return data
    }
    self.table.refresh_data()
}

// view eptStale events
function view_dashboard_stale(vm){
    var self = vm;
    self.historical_tab(true)
    self.view_dashboard(true)
    self.view("dashboard_stale")
    self.table.url("/api/ept/stale")
    var headers = [
        {"title": "Time", "name":"ts_str", "sort_name":"events.0.ts", "sorted":true},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Type", "name":"type"},
        {"title": "Address", "name":"addr"},
        {"title": "Node", "name":"node"},
        {"title": "Event Count", "name":"count"},
        {"title": "VRF/BD", "name":"vnid_name", "sort_name":"events.0.vnid_name"} 
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
    })

    self.table.refresh_handler = function(api_data){
        var data=[]
        api_data.objects.forEach(function(elem){
            if("ept.stale" in elem){
                var obj = new eptStale()
                obj.fromJS(elem["ept.stale"])
                data.push(obj)
            }
        })
        return data
    }
    self.table.refresh_data()
}

// view latest events
function view_dashboard_latest_events(vm){
    var self = vm;
    self.view_dashboard(true)
    self.view("dashboard_latest_events")
    self.table.url("/api/ept/history")
    var headers = [
        {"title": "Time", "name":"ts_str", "sort_name":"events.0.ts", "sorted":true},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Status", "name":"status_str", "sort_name":"events.0.status"},
        {"title": "Type", "name":"type"},
        {"title": "Address", "name":"addr"},
        {"title": "Node", "name":"node"},
        {"title": "VRF/BD", "name":"vnid_name", "sort_name":"events.0.vnid_name"} 
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
    })

    self.table.refresh_handler = function(api_data){
        var data=[]
        api_data.objects.forEach(function(elem){
            if("ept.history" in elem){
                var obj = new eptHistory()
                obj.fromJS(elem["ept.history"])
                data.push(obj)
            }
        })
        return data
    }
    self.table.refresh_data()
}

// view eptRapid events
function view_dashboard_rapid(vm){
    var self = vm;
    self.historical_tab(true)
    self.view_dashboard(true)
    self.view("dashboard_rapid")
    self.table.url("/api/ept/rapid")
    var headers = [
        {"title": "Time", "name":"ts_str", "sort_name":"events.ts", "sorted":true},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Type", "name":"type"},
        {"title": "Address", "name":"addr"},
        {"title": "Event Count", "name":"count"},
        {"title": "Rate (per minute)", "name":"rate", "sort_name":"events.rate"},
        {"title": "VRF/BD", "name":"vnid_name", "sort_name":"events.vnid_name"} 
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
    })

    self.table.refresh_handler = function(api_data){
        var data=[]
        api_data.objects.forEach(function(elem){
            if("ept.rapid" in elem){
                var obj = new eptRapid()
                obj.fromJS(elem["ept.rapid"])
                data.push(obj)
            }
        })
        return data
    }
    self.table.refresh_data()
}

// view eptRemediate events
function view_dashboard_remediate(vm){
    var self = vm;
    self.view_dashboard(true)
    self.view("dashboard_remediate")
    self.table.url("/api/ept/remediate")
    var headers = [
        {"title": "Time", "name":"ts_str", "sort_name":"events.ts", "sorted":true},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Type", "name":"type"},
        {"title": "Node", "name":"node"},
        {"title": "Address", "name":"addr"},
        {"title": "Event Count", "name":"count"},
        {"title": "Action", "name":"action", "sortable":false},
        {"title": "Reason", "name":"reason", "sortable":false},
        {"title": "VRF/BD", "name":"vnid_name", "sort_name":"events.vnid_name"} 
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
    })

    self.table.refresh_handler = function(api_data){
        var data=[]
        api_data.objects.forEach(function(elem){
            if("ept.remediate" in elem){
                var obj = new eptRemediate()
                obj.fromJS(elem["ept.remediate"])
                data.push(obj)
            }
        })
        return data
    }
    self.table.refresh_data()
}

//endpoint detail handler
function view_endpoint_detail(vm, args){
    var self = vm;
    self.view("endpoint_detail")
    self.view_endpoint(true)
    self.endpoint_detail_fabric(args[0])
    self.endpoint_detail_vnid(args[1])
    self.endpoint_detail_addr(args[2])
    var tab="history"
    if(args.length>3){
        switch(args[3]){
            case "detailed": tab="detailed"; break;
            case "history": tab="history"; break;
            case "moves": tab="moves"; break
            case "offsubnet": tab="offsubnet"; break;
            case "stale": tab="stale"; break;
            case "rapid": tab="rapid"; break;
            case "remediate": tab="remediate"; break
        }
    }
    self.endpoint_detail_tab(tab)
    self.table.back_enabled(true)

    var endpoint_detail_url = ""
    var event_type = generalEvent

    var get_endpoint_detail_url = function(classname){
        //unique url for endpoint and moves, other are all filters. However, moves may not exists
        //and instead of adding 404 handlers, will only use direct url for endpoint
        if(classname == "endpoint"){
            var url = "/api/uni/fb-"+self.endpoint_detail_fabric()+"/"+classname
            url+= "/vnid-"+self.endpoint_detail_vnid()+"/addr-"+self.endpoint_detail_addr()
            return url
        }
        var url = "/api/ept/"+classname+"?filter=and("
        url+= "eq(\"fabric\",\""+self.endpoint_detail_fabric()+"\"),"
        url+= "eq(\"vnid\","+self.endpoint_detail_vnid()+"),"
        url+= "eq(\"addr\",\""+self.endpoint_detail_addr()+"\"))"
        return url
    }
    self.view_endpoint_set_dependencies = function(){
        //different view based selected endpoint_detail_tab which is set by view
        var headers = []
        var toggles = []
        event_type = generalEvent
        if(self.endpoint_detail_tab()=="detailed"){
            endpoint_detail_url = get_endpoint_detail_url("history")
            headers = [ 
                {"title": "Time", "name":"ts_str", "sorted":true, "sort_direction":"desc"},
                {"title": "Node", "name":"node_str", "sort_name":"node"},
                {"title": "Status", "name":"status"},
                {"title": "Interface", "name":"intf_name"},
                {"title": "Encap", "name":"encap_str"},
                {"title": "Flags", "name":"flags_str"},
                {"title": "pcTag", "name":"pctag_str", "sort_name":"pctag"},
                {"title": "Remote", "name":"remote_str", "sort_name":"remote"},
                {"title": "EPG", "name":"epg_name_str"}
            ]
            if(self.current_endpoint.type()!="mac"){
                headers.splice(headers.length-1, 0, {"title":"Mac", "name":"mac_str"})
            }
        } else if(self.endpoint_detail_tab() == "history") {
            endpoint_detail_url = get_endpoint_detail_url("endpoint")
            headers = [ 
                {"title": "Time", "name":"ts_str", "sorted":true, "sort_direction":"desc"},
                {"title": "Status", "name":"status"},
                {"title": "Local Node", "name":"node_str"},
                {"title": "Interface", "name":"intf_name"},
                {"title": "Encap", "name":"encap_str"},
                {"title": "EPG", "name":"epg_name_str"}
            ]
            if(self.current_endpoint.type()!="mac"){
                headers.splice(headers.length-1, 0, {"title":"Mac", "name":"mac_str"})
            }
        } else if(self.endpoint_detail_tab() == "moves") {
            event_type = moveEvent
            endpoint_detail_url = get_endpoint_detail_url("move")
            headers = [ 
                {"title": "Time", "name":"ts_str", "sorted":true, "sort_direction":"desc"},
                {"title": "Direction", "name":"direction", "sortable":false},
                {"title": "Local Node", "name":"node_str", "sortable":false},
                {"title": "Interface", "name":"intf_name", "sortable":false},
                {"title": "Encap", "name":"encap", "sortable":false},
                {"title": "EPG", "name":"epg_name", "sortable":false}
            ]
            if(self.current_endpoint.type()!="mac"){
                headers.splice(headers.length-1, 0, {"title":"Mac", "name":"mac_str"})
            }
        } else if(self.endpoint_detail_tab() == "offsubnet") {
            endpoint_detail_url = get_endpoint_detail_url("offsubnet")
            headers = [ 
                {"title": "Time", "name":"ts_str", "sorted":true, "sort_direction":"desc"},
                {"title": "Node", "name":"node_str", "sort_name":"node"},
                {"title": "Interface", "name":"intf_name"},
                {"title": "Encap", "name":"encap_str"},
                {"title": "Remote", "name":"remote_str", "sort_name":"remote"},
                {"title": "EPG", "name":"epg_name_str"}
            ]
        } else if(self.endpoint_detail_tab() == "stale") {
            endpoint_detail_url = get_endpoint_detail_url("stale")
            headers = [ 
                {"title": "Time", "name":"ts_str", "sorted":true, "sort_direction":"desc"},
                {"title": "Node", "name":"node_str", "sort_name":"node"},
                {"title": "Interface", "name":"intf_name"},
                {"title": "Encap", "name":"encap_str"},
                {"title": "Remote", "name":"remote_str", "sort_name":"remote"},
                {"title": "Expected-Remote", "name":"expected_remote_str", "sort_name":"expected_remote"},
                {"title": "EPG", "name":"epg_name_str"}
            ]
        } else if(self.endpoint_detail_tab() == "rapid") {
            endpoint_detail_url = get_endpoint_detail_url("rapid")
            event_type = rapidEvent
            headers = [ 
                {"title": "Time", "name":"ts_str", "sorted":true, "sort_direction":"desc"},
                {"title": "Event Count", "name":"count"},
                {"title": "Event Rate (per-minute)", "name":"rate_str", "sort_name":"rate"}
            ]
        } else if(self.endpoint_detail_tab() == "remediate") {
            endpoint_detail_url = get_endpoint_detail_url("remediate")
            event_type = remediateEvent
            headers = [ 
                {"title": "Time", "name":"ts_str", "sorted":true, "sort_direction":"desc"},
                {"title": "Node", "name":"node"},
                {"title": "Action", "name":"action_str"},
                {"title": "Reason", "name":"reason_str"}
            ]
        } else {
            endpoint_detail_url = ""
        }
        self.table.headers([])
        headers.forEach(function(h){self.table.headers.push(new gHeader(h))})
        self.table.toggles([])
        toggles.forEach(function(t){self.table.toggles.push(new gToggle(t))})
    }

    self.view_endpoint_detail_refresh = function(){
        self.refresh_endpoint(function(){
            //different view based selected endpoint_detail_tab which is set by view
            self.view_endpoint_set_dependencies()
            self.table.rows([])
            if(endpoint_detail_url.length>0){
                self.table.isLoading(true)
                json_get(endpoint_detail_url, function(data){
                    self.table.isLoading(false)
                    var result_count = 0
                    var result_count_wrapped = 0
                    var rows = []
                    data.objects.forEach(function(elem){
                        var classname = Object.keys(elem)[0]
                        var node = null
                        var event_count = 0
                        if("node" in elem[classname]){ node = elem[classname].node }
                        if("events" in elem[classname]){
                            elem[classname].events.forEach(function(e){
                                var general_event = new event_type()
                                general_event.fromJS(e)
                                general_event.fabric(elem[classname].fabric)
                                if(node!=null){ general_event.node(node) }
                                rows.push(new gRow(general_event))
                                event_count++
                            })
                        }
                        if(event_count>0 && "count" in elem[classname]){
                            result_count_wrapped+=event_count
                            result_count+=elem[classname].count
                        }
                    })
                    self.table.result_count(result_count)
                    self.table.result_count_wrapped(result_count_wrapped)
                    self.table.rows(rows)
                    self.table.client_sort()
                })
            }
        })
    
    }
    self.table.custom_refresh = self.view_endpoint_detail_refresh
    self.view_endpoint_detail_refresh()
}

function common_viewModel() {
    var self = this; 
    self.isLoading = ko.observable(false)
    self.view = ko.observable("index")
    self.table = new gTable()
    self.app_mode = ko.observable(executing_in_app_mode())
    self.admin_role = ko.observable(true)       
    self.fabrics = ko.observableArray([])
    self.current_fabric_name = ko.observable("")
    self.current_fabric = new fabric()
    self.current_fabric_not_found = ko.observable(false)
    self.historical_tab = ko.observable(false)
    self.view_dashboard = ko.observable(false)
    self.view_endpoint = ko.observable(false)
    self.view_edit_fabric = ko.observable(false)
    self.edit_fabric_tab = ko.observable("")
    self.fabric_isLoading = ko.observable(false)
    self.clear_endpoint_isLoading = ko.observable(false)
    self.endpoint_detail_fabric = ko.observable("")
    self.endpoint_detail_vnid = ko.observable(0)
    self.endpoint_detail_addr = ko.observable("")
    self.endpoint_detail_tab = ko.observable("")
    self.current_endpoint_not_found = ko.observable(false)
    self.current_endpoint = new eptEndpoint()
    self.endpoint_isLoading = ko.observable(false)
    self.new_fabric_name = ko.observable("")

    // view functions 
    self.init = function(){
        self.isLoading(false)
        self.endpoint_isLoading(false)
        self.view_dashboard(false)
        self.view_endpoint(false)
        self.view_edit_fabric(false)
        self.edit_fabric_tab("")
        self.new_fabric_name("")
        self.fabric_isLoading(false)
        self.clear_endpoint_isLoading(false)
        self.current_fabric_not_found(false)
        self.historical_tab(false)
        self.endpoint_detail_fabric("")
        self.endpoint_detail_vnid(0)
        self.endpoint_detail_addr("")
        self.endpoint_detail_tab("")
        self.current_endpoint_not_found(false)
        self.table.init()
    }

    ///////////////////////////////////////////////////////////////////////////////////////////////
    ///////////////////////////////////////////////////////////////////////////////////////////////
    //
    // fabric functions
    //
    ///////////////////////////////////////////////////////////////////////////////////////////////
    ///////////////////////////////////////////////////////////////////////////////////////////////

    //refresh fabric state and trigger provided callback once full refresh has completed
    self.refresh_fabrics = function(success, fab){
        if(success===undefined){ success = function(){}}
        if(fab===undefined){ fab = null}
        var inflight = 0
        var check_all_complete = function(refreshed_fabric){
            inflight--
            if(inflight==0){
                if(self.current_fabric_name()==refreshed_fabric.fabric()){
                    self.current_fabric.fromJS(refreshed_fabric.toJS())
                }
                success()
            }
        }
        json_get("/api/fabric?include=fabric&sort=fabric", function(data){
            var fabrics = []
            if(fab!=null){ self.current_fabric_not_found(true) }
            data.objects.forEach(function(elem){
                var f = new fabric(elem.fabric.fabric)
                fabrics.push(f)
                //support for refreshing a single fabric
                //if single fab was provided for refresh, then only trigger refresh for that fabric
                if(fab==null || f.fabric()==fab){
                    inflight++
                    f.refresh(check_all_complete)
                    self.current_fabric_not_found(false)
                }
            })
            self.fabrics(fabrics)
            //possible that no fabrics where found or filtered fabric does not exists, in which 
            //case we need to trigger success function as there are no inflight requests
            if(inflight==0){success()}
        })
    }

    //delete the currently viewed fabric
    self.delete_fabric = function(){
        var msg = '<h3>Wait</h3><div>Are you sure you want to delete ' +
        '<span class="text-bold">'+self.current_fabric.fabric()+'</span>. '+
        'This operation will delete all endpoint history for the corresponding fabric. ' +
        'This action cannot be undone.';
        confirmModal(msg, true, function(){
            var url="/api/uni/fb-"+self.current_fabric.fabric()
            self.fabric_isLoading(true)
            json_delete(url, {}, function(){
                self.fabric_isLoading(false)
                forward("#/")
            })
        })
    }
    //create a new fabric
    self.create_fabric = function(){
        var js = {"fabric": self.new_fabric_name() }
        if(js.fabric.length>0){
            var url = "/api/fabric"
            self.fabric_isLoading(true)
            json_post(url, js, function(data){
                hideModal()
                forward("#/fb-"+self.new_fabric_name()+"/settings")
            })
        }
    }
    //save current fabric settings
    self.save_fabric = function(){
        var f = self.current_fabric
        var js = {
            "apic_cert": f.apic_cert(),
            "apic_hostname": f.apic_hostname(),
            "apic_username": f.apic_username(),
            "ssh_username": f.ssh_username(),
            "max_events": f.max_events()
        }
        if(f.apic_password().length>0){ js["apic_password"] = f.apic_password() }
        if(f.ssh_password().length>0){ js["ssh_password"] = f.ssh_password() }
        // get settings values, all settings can be applied at once
        var settings_js = self.current_fabric.settings.toJS()
        var url="/api/uni/fb-"+self.current_fabric.fabric()
        self.fabric_isLoading(true)
        json_patch(url, js, function(){
            var url2 = "/api/uni/fb-"+self.current_fabric.fabric()+"/settings-default"
            json_patch(url2, settings_js, function(data){
                //re-check credentials on success and then
                //if they are good prompt user to restart the fabric, else alert user of failure
                var url = "/api/uni/fb-"+self.current_fabric.fabric()+"/verify"
                json_post(url, {}, function(data){
                    self.fabric_isLoading(false)
                    if(data.success){
                        if(self.current_fabric.status()=="running"){
                            var msg = '<div>' +
                                  'Changes successfully saved. You must restart the fabric ' +
                                  'monitor for your changes to take effect.<br><br> ' +
                                  'Restart monitor for <span class="text-bold">'+self.current_fabric.fabric()+'</span> now?' +
                                  '</div>'
                            confirmModal(msg, true, function(){
                                self.fabric_isLoading(true)
                                var url3="/api/uni/fb-"+self.current_fabric.fabric()+"/stop"
                                json_post(url3, {}, function(data){
                                    var url4="/api/uni/fb-"+self.current_fabric.fabric()+"/start"
                                    json_post(url4, {}, function(data){
                                        self.fabric_isLoading(false)
                                        self.refresh_fabrics(undefined, self.current_fabric.fabric())
                                    })
                                })
                            })
                        }
                    }else{
                        var apic_success = (data.apic_error.length==0)
                        var ssh_success = (data.ssh_error.length==0)
                        var msg = '<h3>Credential verification failed</h3>';
                        if(apic_success){
                            msg+= '<div class="row">'+
                                    '<div class="col-md-2"><span class="text-bold">APIC Credentials</span></div>' +
                                    '<div class="col-md-10"><span class="label label--success">success</span></div>' +
                                 '</div>'
                        } else {
                            msg+= '<div class="row">'+
                                    '<div class="col-md-2"><span class="text-bold">APIC Credentials</span></div>' +
                                    '<div class="col-md-10"><span class="label label--warning-alt">failed</span> ' +
                                     data.apic_error + '</div>' +
                                  '</div>'
                        }
                        if(ssh_success){
                            msg+= '<div class="row">'+
                                    '<div class="col-md-2"><span class="text-bold">SSH Credentials</span></div>' +
                                    '<div class="col-md-10"><span class="label label--success">success</span></div>' +
                                 '</div>'
                        } else {
                            msg+= '<div class="row">'+
                                    '<div class="col-md-2"><span class="text-bold">SSH Credentials</span></div>' +
                                    '<div class="col-md-10"><span class="label label--warning-alt">failed</span> ' +
                                    data.ssh_error + '</div>' +
                                  '</div>'
                        }
                        showInfoModal(msg, true)
                    }
                })
            })
        })
    }
    // test notification
    self.test_fabric_notification = function(notify_type){
        if(notify_type=="syslog" || notify_type=="email"){
            var url="/api/uni/fb-"+self.current_fabric.fabric()+"/settings-default/test/"+notify_type
            self.fabric_isLoading(true)
            json_post(url, {}, function(data){
                self.fabric_isLoading(false)
                var msg = "Test "+notify_type+" sent. Please validate the message was received."
                showInfoModal(msg)
            }, function(json, status_code, status_text){
                self.fabric_isLoading(false)
                generic_ajax_error(json, status_code, status_text)
            })
        }
    }


    ///////////////////////////////////////////////////////////////////////////////////////////////
    ///////////////////////////////////////////////////////////////////////////////////////////////
    //
    // endpoint functions
    //
    ///////////////////////////////////////////////////////////////////////////////////////////////
    ///////////////////////////////////////////////////////////////////////////////////////////////

    // commonly used api
    self.get_endpoint_api = function(){
        var url = "/api/uni/fb-"+self.endpoint_detail_fabric()+"/endpoint"
        url+="/vnid-"+self.endpoint_detail_vnid()
        url+="/addr-"+self.endpoint_detail_addr()
        return url
    }

    //refresh single endpoint and trigger provided callback once refresh is complete
    //endpoint is determined by endpoint_detail_fabric/vnid/addr - not this function will also set
    //self.current_endpoint to eptEndpoint object with all appropriate data populated. If the 
    //endpoint is not found (404 error), then set current_endpoint_not_found to true
    self.refresh_endpoint = function(success){
        if(success===undefined){ success = function(){}}
        var url = self.get_endpoint_api()
        self.endpoint_isLoading(true)
        json_get(url, function(data){
            if(data.objects.length>0 && "ept.endpoint" in data.objects[0]){
                self.current_endpoint_not_found(false)
                self.current_endpoint.fromJS(data.objects[0]["ept.endpoint"])
                var inflight = 6
                var check_all_complete = function(){
                    inflight--
                    if(inflight==0){
                        self.endpoint_isLoading(false)
                        return success()
                    }
                }
                var flt = [
                    "eq(\"fabric\",\""+self.endpoint_detail_fabric()+"\")",
                    "eq(\"vnid\","+self.endpoint_detail_vnid()+")", 
                    "eq(\"addr\",\""+self.endpoint_detail_addr()+"\")"
                ]
                //get list of is_stale and is_offsubnet nodes from history table
                var url1="/api/ept/history?include=is_offsubnet,is_stale,node&filter=and("
                url1+= flt.join(",")+","
                url1+="or(eq(\"is_stale\",true),eq(\"is_offsubnet\",true)))"
                json_get(url1, function(data){
                    var stale_nodes = []
                    var offsubnet_nodes = []
                    data.objects.forEach(function(elem){
                        h=elem["ept.history"]
                        if(h.is_stale){stale_nodes.push(h.node)}
                        if(h.is_offsubnet){offsubnet_nodes.push(h.node)}
                    })
                    stale_nodes.sort()
                    offsubnet_nodes.sort()
                    self.current_endpoint.stale_nodes(stale_nodes)
                    self.current_endpoint.offsubnet_nodes(offsubnet_nodes)
                    check_all_complete()
                })
                // set node count 
                var url2="/api/ept/history?count=1&filter=and("+flt.join(",")+")"
                json_get(url2, function(data){
                    self.current_endpoint.count_nodes(data.count)
                    check_all_complete()
                })
                // set move count 
                var url3="/api/ept/move?include=count&filter=and("+flt.join(",")+")"
                json_get(url3, function(data){
                    var count = 0
                    data.objects.forEach(function(obj){
                        if("ept.move" in obj){count+= obj["ept.move"].count}
                    })
                    self.current_endpoint.count_moves(count)
                    check_all_complete()
                })
                // set offsubnet count 
                var url4="/api/ept/offsubnet?include=count&filter=and("+flt.join(",")+")"
                json_get(url4, function(data){
                    var count = 0
                    data.objects.forEach(function(obj){
                        if("ept.offsubnet" in obj){count+= obj["ept.offsubnet"].count}
                    })
                    self.current_endpoint.count_offsubnet(count)
                    check_all_complete()
                })
                // set stale count 
                var url5="/api/ept/stale?include=count&filter=and("+flt.join(",")+")"
                json_get(url5, function(data){
                    var count = 0
                    data.objects.forEach(function(obj){
                        if("ept.stale" in obj){count+= obj["ept.stale"].count}
                    })
                    self.current_endpoint.count_stale(count)
                    check_all_complete()
                })
                // set rapid count 
                var url6="/api/ept/rapid?include=count&filter=and("+flt.join(",")+")"
                json_get(url6, function(data){
                    var count = 0
                    data.objects.forEach(function(obj){
                        if("ept.rapid" in obj){count+= obj["ept.rapid"].count}
                    })
                    self.current_endpoint.count_rapid(count)
                    check_all_complete()
                })
            } else {
                console.log("invalid response...")
                self.endpoint_isLoading(false)
                self.current_endpoint_not_found(true)
            }
        },
        function(json, status_code, status_text){
            self.endpoint_isLoading(false)
            if(status_code==404){
                self.current_endpoint_not_found(true)
                return success()
            }else{
                generic_ajax_error(json, status_code, status_text)
            }
        })
    }

    //endpoint user buttons
    self.endpoint_force_refresh = function(){
        var msg = '<h3>Wait</h3><div>Are you sure you want to force a <b>refresh</b> of '+
            '<span class="text-bold">'+self.current_endpoint.addr()+'</span>. This operation will '+
            'query the APIC for the most recent state of the endpoint and then update the local ' +
            'database. It may take a few moments for the updates to be seen.'
        confirmModal(msg, true, function(){
            var url = self.get_endpoint_api()+"/refresh"
            self.endpoint_isLoading(true)
            json_post(url, {}, function(data){
                self.endpoint_isLoading(false)
                self.refresh_endpoint()
            })
        })
    }
    // delete endpoint request
    self.endpoint_force_delete = function(){
        var msg = '<h3>Wait</h3><div>Are you sure you want to <b>delete</b> all information for '+
            '<span class="text-bold">'+self.current_endpoint.addr()+'</span> '+
            'from the local database?<br>Note, this will not affect endpoint state within the fabric'
        confirmModal(msg, true, function(){
            var url = self.get_endpoint_api()+"/delete"
            self.endpoint_isLoading(true)
            json_delete(url, {}, function(data){
                self.endpoint_isLoading(false)
                self.refresh_endpoint()
            })
        })
    }
    self.endpoint_force_clear = function(){
        self.init_clear_endpoint_select()
        showModalClearEndpointForm()
    }


    ///////////////////////////////////////////////////////////////////////////////////////////////
    ///////////////////////////////////////////////////////////////////////////////////////////////
    //
    // Routing/Views
    //
    ///////////////////////////////////////////////////////////////////////////////////////////////
    ///////////////////////////////////////////////////////////////////////////////////////////////

    // set active class for active dashboard tab
    self.dashboard_active_tab = function(tab){
        if(self.view()==tab){ return "active" }
        return ""
    }
    self.edit_fabric_active_tab = function(tab){
        if(self.edit_fabric_tab()==tab){ return "active" }
        return ""
    }
    self.edit_fabric_tab_link = ko.computed(function(){
        return "#/fb-"+self.current_fabric_name()+"/settings"
    })
    // set active class for active endpoint_detail tab
    self.endpoint_detail_active_tab = function(tab){
        if(self.endpoint_detail_tab()==tab){ return "active" }
        return ""
    }
    // endpoint detail tab link is computed based on currently viewed endpoint
    self.endpoint_detail_tab_link = ko.computed(function(){
        var url = "#/fb-"+self.endpoint_detail_fabric()
        url+="/vnid-"+self.endpoint_detail_vnid()
        url+="/addr-"+self.endpoint_detail_addr()
        return url
    })

    // simple same-page routing to support direct anchor links (very basic/static)
    // for now, just /case-# and /case-#/filename-#
    var routes = [
        {"route": "/fb-([^/]+)/history", "view": view_dashboard_fabric_events},
        {"route": "/fb-([^/]+)/settings", "view": view_dashboard_fabric_settings},
        {"route": "/fb-([^/]+)/settings/([a-z]+)", "view": view_dashboard_fabric_settings},
        {"route": "/endpoints", "view": view_dashboard_endpoints},
        {"route": "/moves", "view": view_dashboard_moves},
        {"route": "/offsubnet", "view": view_dashboard_offsubnet},
        {"route": "/stale", "view": view_dashboard_stale},
        {"route": "/rapid", "view": view_dashboard_rapid},
        {"route": "/remediate", "view": view_dashboard_remediate},
        {"route": "/events", "view": view_dashboard_latest_events},
        {"route": "/fb-([^/]+)/vnid-([0-9]+)/addr-([^/]+)", "view": view_endpoint_detail},
        {"route": "/fb-([^/]+)/vnid-([0-9]+)/addr-([^/]+)/([a-z]+)", "view": view_endpoint_detail}
    ]
    self.navigate = function(){
        self.init()
        for (var i in routes) {
            var r = routes[i]
            var regex = new RegExp("^#"+r["route"]+"$")
            var match = regex.exec(window.location.hash)
            if (match != null){
                if(match.length>1){
                    return r["view"](self, match.slice(1, match.length));
                }else{
                    return r["view"](self);
                }
            }
        }
        return view_dashboard_fabric(self);
    }


    ///////////////////////////////////////////////////////////////////////////////////////////////
    ///////////////////////////////////////////////////////////////////////////////////////////////
    //
    // Search bar
    //
    ///////////////////////////////////////////////////////////////////////////////////////////////
    ///////////////////////////////////////////////////////////////////////////////////////////////


    // searchbar handler (if present)
    self.searchBar = null;
    self.init_searchbar = function(){
        //destroy any existing select2 anchored on searchBar
        if(self.searchBar != null){
            try{$("#searchBar").select2("destroy")}catch(err){}
        }
        self.searchBar = $("#searchBar").select2({
            allowClear: true,
            placeholder: "Search MAC or IP address, 00:50:56:01:BB:12, 10.1.1.101, or 2001:a:b::65",
            ajax: {
                url: "/api/ept/endpoint",
                dataType: 'json',
                delay: 250,
                transport: function (params, success, failure){
                    var url_params = [
                        'filter='+params.data.filter,
                        "include=fabric,addr,vnid,type,first_learn",
                        "page-size=20",
                        "sort=addr"
                    ]
                    var url = "/api/ept/endpoint?"+url_params.join("&")
                    var $request = json_get(url, success, failure)
                    $request.then(success);
                    $request.fail(failure);
                    return $request;
                },
                data: function (params) {
                    var term = params.term
                    if(params.term.charAt(0)=="/"){
                        term = params.term.substring(1)
                    } else { 
                        term = "(?i)"+escapeRegExp(params.term)
                    }
                    return {
                        "filter": 'regex("addr","'+term+'")'
                    };
                },
                processResults: function (data, params) {
                    // parse the results into the format expected by Select2
                    params.page = params.page || 1;
                    var results = []
                    for (var i in data.objects){
                        var obj = data.objects[i]
                        if("ept.endpoint" in obj){
                            obj = obj["ept.endpoint"]
                            obj.dn = "/fb-"+obj.fabric+"/vnid-"+obj.vnid+"/addr-"+obj.addr
                            obj.id = obj.dn
                            obj.text = obj.dn
                            if("first_learn" in obj && "vnid_name" in obj.first_learn && 
                                obj.first_learn.vnid_name.length > 0){
                                obj.vnid_name = obj.first_learn.vnid_name
                            } else {
                                obj.vnid_name = "vnid-"+obj.vnid
                            }
                            results.push(obj)
                        }
                    }
                    if("count" in data){
                        results.unshift({"count":data.count})
                    }
                    return {
                        results: results,
                        pagination: {
                            more: false
                        }
                    };
                },
                cache: true
            },
            escapeMarkup: function (markup) { return markup; }, // let our custom formatter work
            minimumInputLength: 4,
            templateResult: function(data) {
                // displaying decode objects and we just want to create html with case and filename
                if ("fabric" in data && "vnid" in data && "addr" in data && "type" in data){
                    type_label = get_endpoint_type_label(data.type)
                    var html = '<div class="row">' +
                        '<div class="col-sm-2"> ' + 
                            '<span class="label label-default">' + data.fabric + '</span>' +
                        '</div>' +
                        '<div class="col-sm-1"> ' + 
                            '<span class="'+type_label+'">' + data.type + '</span>' +
                        '</div>' +
                        '<div class="col-sm-2"> ' +
                            '<span>' + data.addr + '</span>' +
                        '</div>' +
                        '<div class="col-sm-6"> ' +
                            '<span>' + data.vnid_name + '</span>' +
                        '</div>' +
                    '</div>';
                    return html
                }
                else if("count" in data){
                    return 'Matched: <strong>'+data.count+'</strong>'
                }
            },
            templateSelection: function(repo){ 
                return repo.full_name || repo.text; 
            }
        });
        self.searchBar.on("select2:select", function (evt) { 
            if (!evt) { return; } 
            if (!evt.params || !evt.params.data){ return; }
            if("dn" in evt.params.data){
                forward(evt.params.data.dn)
                self.searchBar.val(null).trigger('change')
            }
        });
    }

    // clear node select option
    self.clearEndpointSelect = null;
    self.init_clear_endpoint_select = function(){
        //destroy any existing select2 anchored on searchBar
        if(self.clearEndpointSelect != null){
            $("#clearEndpointSelect").empty()
            try{$("#clearEndpointSelect").select2("destroy")}catch(err){}
        }
        self.clearEndpointSelect = $("#clearEndpointSelect").select2({
            allowClear: true,
            placeholder: "Select nodes to execute clear endpoint",
            escapeMarkup: function (markup) { return markup; }, // let our custom formatter work
            tags: true,
            data: [],
            minimumInputLength: 2,
            templateSelection: function(obj){
                return obj.text.replace(/ /g, " ")
            }
        });
        self.clearEndpointSelect.on("select2:select", function (evt) { 
            if (!evt) { return; } 
            if (!evt.params || !evt.params.data){ return; }
            if("text" in evt.params.data){
                var val = data.text
                //no-op for now, validation on submit
            }
        });
    }

    // submit clear endpoint
    self.submit_clear_endpoint = function(){
        var nodes=[]
        self.clearEndpointSelect.val().forEach(function(elem){
            elem.split(",").forEach(function(val){
                val = val.replace(/^[ ]*/g, "")
                val = val.replace(/[ ]*$/g, "")
                if(val.match(/^[0-9]+$/)!=null){
                    val = parseInt(val)
                    if(!nodes.includes(val)){ nodes.push(val) }
                } else if(val.match(/^[0-9]+[ ]*-[ ]*[0-9]+$/)!=null){
                    var val1 = parseInt(val.split("-")[0])
                    var val2 = parseInt(val.split("-")[1])
                    if(val1 > val2){
                        for(var i=val2; i<=val1; i++){ 
                            if(!nodes.includes(i)){ nodes.push(i) } 
                        }
                    } else {
                        for(var i=val1; i<=val2; i++){ 
                            if(!nodes.includes(i)){ nodes.push(i) } 
                        }
                    }
                }
            })
        })
        if(nodes.length==0){
            var msg = "Please select one or more valid nodes to execute clear command"
            showInfoModal(msg)
        } else {
            var url = self.get_endpoint_api()+"/clear"
            self.clear_endpoint_isLoading(true) 
            json_post(url, {"nodes": nodes }, function(data){
                self.clear_endpoint_isLoading(false)
                hideModal()
                if(!data.success){
                    showAlertModal(data.error)
                }
            })
        }
    }
}


var page_vm
$().ready(function(){
    var self = new common_viewModel();
    page_vm = self
    ko.applyBindings(self);
    $("main").css("display","block")

    //add listener for hash change
    $(window).on("hashchange", function(){self.navigate();})

    //initialize search bars if present
    self.init_searchbar()
    self.init_clear_endpoint_select()

    //trigger navigation on load
    self.navigate()

    // listen for/refresh app token when running in app mode
    if(self.app_mode()){
        appTokenRefresh()
    } else {
        // verify we are authenticated via check to app-status/manager (which also verifies that
        // manager is running). If unauthenticated, display login 
        
    }
})


