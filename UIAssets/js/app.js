
/* global/consistent colors for endpoint types */
label_mac  = 'label label--warning-alt'
label_ipv4 = 'label label--vibblue'
label_ipv6 = 'label label--indigo'
label_status_running = 'label label--success'
label_status_stopped = 'label label--dkgray'
function get_endpoint_type_label(type){
    switch(type){
        case "mac": return label_mac;
        case "ipv4": return label_ipv4;
        case "ipv6": return label_ipv6;
    }
    return label_ipv4
}
function get_status_label(st){
    switch(st){
        case 'running': return label_status_running
        case 'stopped': return label_status_stopped
    }
    return label_status_stopped
}


function fabricEvent(){
    baseModelObject.call(this)
    var self = this
    self.timestamp = ko.observable(0)
    self.status = ko.observable("")
    self.description = ko.observable("")
    self.ts_str = ko.computed(function(){
        return timestamp_to_string(self.timestamp())
    }) 

    // custom cell formatting per attribute
    self.formatter = function(attr, text){
        if(attr == "status"){
            var alabel = ""
            switch(text){
                case "running": alabel = "label--success" ; break;
                case "starting":alabel = "label--info" ; break;
                case "stopped": alabel = "label--dkgray" ; break;
                case "failed":  alabel = "label--danger"; break;
                default:        alabel = "label--default";
            }
            return '<span class="label '+alabel+'">'+text+'</span>'
        } else if(attr == "description"){
            if(text.length==0){ return "-" }
            return text
        }
        return text
    }
}

function fabricSettings(){
    baseModelObject.call(this)
    var self = this
    self.settings = ko.observable("default")
    self.email_address = ko.observable("")
    self.syslog_server = ko.observable("")
    self.syslog_port = ko.observable(514)
    self.notify_move_email = ko.observable(false)
    self.notify_stale_email = ko.observable(false)
    self.notify_offsubnet_email = ko.observable(false)
    self.notify_clear_email = ko.observable(false)
    self.notify_rapid_email = ko.observable(false)
    self.notify_move_syslog = ko.observable(false)
    self.notify_stale_syslog = ko.observable(false)
    self.notify_offsubnet_syslog = ko.observable(false)
    self.notify_clear_syslog = ko.observable(false)
    self.notify_rapid_syslog = ko.observable(false)
    self.auto_clear_stale = ko.observable(false)
    self.auto_clear_offsubnet = ko.observable(false)
    self.anaylze_move = ko.observable(true)
    self.anaylze_offsubnet = ko.observable(true)
    self.anaylze_stale = ko.observable(true)
    self.anaylze_rapid = ko.observable(true)
    self.refresh_rapid = ko.observable(true)
    self.max_per_node_endpoint_events = ko.observable(64)
    self.max_endpoint_events = ko.observable(64)
    self.queue_init_events = ko.observable(true)
    self.queue_init_epm_events = ko.observable(true)
    self.stale_no_local = ko.observable(true)
    self.stale_multiple_local = ko.observable(true)
    self.rapid_threshold = ko.observable(1024)
    self.rapid_holdtime = ko.observable(600)
}

function fabric(fabric_name) {
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"events": fabricEvent}
    self.fabric = ko.observable(fabric_name)
    self.settings = new fabricSettings()
    self.apic_username = ko.observable("")
    self.apic_password = ko.observable("")
    self.apic_hostname = ko.observable("")
    self.apic_cert = ko.observable("")
    self.ssh_username = ko.observable("")
    self.ssh_password = ko.observable("")
    self.events = ko.observableArray([])
    self.event_count = ko.observable(0)
    self.status = ko.observable("")
    self.count_mac = ko.observable(".")
    self.count_ipv4 = ko.observable(".")
    self.count_ipv6 = ko.observable(".")
    self.loading_fabric = ko.observable(false)
    self.loading_settings = ko.observable(false)
    self.loading_status = ko.observable(false)
    self.loading_count_mac = ko.observable(false)
    self.loading_count_ipv4 = ko.observable(false)
    self.loading_count_ipv6 = ko.observable(false)

    self.isLoading = ko.computed(function(){
        return (self.loading_fabric() || self.loading_settings() || self.loading_status() || 
                self.loading_count_mac() || self.loading_count_ipv4() || self.loading_count_ipv6())
    })

    // custom cell formatting per attribute
    self.formatter = function(attr, text){
        if(attr == "status"){
            return '<span class="'+get_status_label(text)+'">'+text+'</span>'
        } else if (attr == "fabric"){
            return '<span class="text-bold">'+text+'</span>'
        }
        return text
    }

    // refresh full state for this fabric (fabric, settings, status, and counts)
    self.refresh = function(success){
        if(success===undefined){ success = function(){}}
        self.loading_fabric(true)
        self.loading_settings(true)
        self.loading_status(true)
        self.loading_count_mac(true)
        self.loading_count_ipv4(true)
        self.loading_count_ipv6(true)
        var base = "/api/uni/fb-"+self.fabric()
        var count_base = "/api/ept/endpoint?count=1&filter=and(eq(\"fabric\",\""+self.fabric()+"\"),"
        json_get(base, function(data){
            if(data.objects.length>0){
                self.fromJS(data.objects[0].fabric)
            }
            self.loading_fabric(false)
            if(!self.isLoading()){success()}
        })
        json_get(base+"/settings-default", function(data){
            if(data.objects.length>0){
                self.settings.fromJS(data.objects[0]["ept.settings"])
            }
            self.loading_settings(false)
            if(!self.isLoading()){success()}
        })
        json_get(base+"/status", function(data){
            self.status(data.status)
            self.loading_status(false)
            if(!self.isLoading()){success()}
        })
        json_get(count_base+"eq(\"type\",\"mac\"))", function(data){
            self.count_mac(data.count)
            self.loading_count_mac(false)
            if(!self.isLoading()){success()}
        })
        json_get(count_base+"eq(\"type\",\"ipv4\"))", function(data){
            self.count_ipv4(data.count)
            self.loading_count_ipv4(false)
            if(!self.isLoading()){success()}
        })
        json_get(count_base+"eq(\"type\",\"ipv6\"))", function(data){
            self.count_ipv6(data.count)
            self.loading_count_ipv6(false)
            if(!self.isLoading()){success()}
        })
    }
}

// general event used by eptEndpoint, eptHistory, eptStale, etc...
function generalEvent(){
    baseModelObject.call(this)
    var self = this
    self.ts = ko.observable(0)
    self.status = ko.observable("")
    self.intf_id = ko.observable("")
    self.intf_name = ko.observable("")
    self.pctag = ko.observable(0)
    self.encap = ko.observable("")
    self.rw_mac = ko.observable("")
    self.rw_bd = ko.observable(0)
    self.epg_name = ko.observable("")
    self.vnid_name = ko.observable("")
    self.node = ko.observable(0)
    self.remote = ko.observable(0)
    self.classname = ko.observable("")
    self.flags = ko.observableArray([])
    self.ts_str = ko.computed(function(){
        return timestamp_to_string(self.ts())
    }) 
}

function moveEvent(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"src": generalEvent, "dst":generalEvent }
    self.src = new generalEvent()
    self.dst = new generalEvent()
    self.ts_str = ko.computed(function(){
        return self.dst.ts_str()
    })
}

function eptEndpoint(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"events": generalEvent, "first_learn":generalEvent }
    self.first_learn = new generalEvent()
    self.fabric = ko.observable("")
    self.vnid = ko.observable(0)
    self.addr = ko.observable("")
    self.type = ko.observable("")
    self.is_stale = ko.observable(false)
    self.is_offsubnet = ko.observable(false)
    self.is_rapid = ko.observable(false)
    self.is_rapid_ts = ko.observable(0)
    self.events = ko.observableArray([])
    self.count = ko.observable(0)

    //set to events.0 or first_learn with preference over events.0
    self.vnid_name = ko.computed(function(){
        var name = ""
        if(self.events().length>0 && self.events()[0].vnid_name().length>0){ 
            name = self.events()[0].vnid_name(); 
        }
        else{ name = self.first_learn.vnid_name() }
        if(name.length>0){ return name }
        return "-"
    })
    self.epg_name = ko.computed(function(){
        var name = ""
        if(self.events().length>0 && self.events()[0].epg_name().length){ 
            name = self.events()[0].epg_name(); 
        }
        else{ name = self.first_learn.epg_name() }
        if(name.length>0){ return name }
        return "-"
    })
    // custom cell formatting per attribute
    self.formatter = function(attr, text){
        if(attr == "type"){
            type_label = get_endpoint_type_label(data.type)
            return '<span class="'+get_endpoint_type_label(text)+'">'+text+'</span>'
        }
        else if(attr == "addr"){
            var url = '#/fb-'+self.fabric()+'/vnid-'+self.vnid()+'/addr-'+self.addr()
            return '<a href="'+url+'">'+text+'</a>'
        }
        return text
    }
}

function eptMove(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"events": moveEvent }
    self.fabric = ko.observable("")
    self.vnid = ko.observable(0)
    self.addr = ko.observable("")
    self.type = ko.observable("")
    self.events = ko.observableArray([])
    self.count = ko.observable(0)

    //get ts_str from first event
    self.ts_str = ko.computed(function(){
        if(self.events().length>0){ return self.events()[0].dst.ts_str() }
        return "-"
    })
    // get vnid_name from events.0
    self.vnid_name = ko.computed(function(){
        var name = ""
        if(self.events().length>0 && self.events()[0].dst.vnid_name().length>0){ 
            name = self.events()[0].dst.vnid_name(); 
        }
        if(name.length>0){ return name }
        return "-"
    })
    // custom cell formatting per attribute
    self.formatter = function(attr, text){
        if(attr == "type"){
            type_label = get_endpoint_type_label(data.type)
            return '<span class="'+get_endpoint_type_label(text)+'">'+text+'</span>'
        }
        else if(attr == "addr"){
            var url = '#/fb-'+self.fabric()+'/vnid-'+self.vnid()+'/addr-'+self.addr()
            return '<a href="'+url+'">'+text+'</a>'
        }
        return text
    }
}



// receive instance of view modal and update table to fabric view
function view_dashboard_fabric(vm){
    var self = vm;

    //build callbacks for each action
    var click_history = function(fab){
        if("fabric" in fab){
            forward("/fb-"+fab.fabric()+"/history")
        }
    }
    var headers = [
        {"title":"Name", "name":"fabric", "sortable":false},
        {"title":"Status", "name": "status", "sortable":false},
        {"title": "MACs", "name":"count_mac", "sortable":false},
        {"title": "IPv4", "name":"count_ipv4", "sortable":false},
        {"title": "IPv6", "name":"count_ipv6", "sortable":false},
        {"title": "Control", "name":"control", "sortable":false, "control":[
            new gCtrl({"tip":"Start", "status":"success", "icon":"icon-right-arrow-contained"}),
            new gCtrl({"tip":"Stop", "status":"negative", "icon":"icon-stop"}),
            new gCtrl({"tip":"Edit", "status":"gray-ghost", "icon":"icon-edit"}),
            new gCtrl({"tip":"History", "status":"secondary", "icon":"icon-chevron-right",
                        "click":click_history})
        ]}
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
    })

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
function view_dashboard_fabric_events(vm){
    var self = vm;
    self.table.back_enabled(true)
    var headers = [
        {"title": "Time", "name":"ts_str", "sortable":false},
        {"title": "Status", "name":"status", "sortable":false},
        {"title": "Description", "name":"description", "sortable":false}
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
    })
    // get fabric object for current view fabric from self.fabrics
    var update_rows = function(){
        var rows = []
        if(self.current_fabric!=null){
            self.current_fabric.events().forEach(function(elem){
                rows.push(new gRow(elem))
            })
        }else{
            self.table.no_data_message("fabric '"+self.current_fabric_name()+"' not found")
        }
        self.table.title(self.current_fabric_name())
        self.table.rows(rows)
        self.table.result_count_wrapped(self.current_fabric.event_count())
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
    if(self.current_fabric == null || self.current_fabric.fabric()!=self.current_fabric_name()){
        self.view_dashboard_fabric_events_refresh()
    }else{
        update_rows()
    }
}

// view eptEndpoint events
function view_dashboard_endpoints(vm){
    var self = vm;
    self.table.url("/api/ept/endpoint")
    var headers = [
        {"title": "Fabric", "name":"fabric", "sortable": false},
        {"title": "Type", "name":"type", "sortable": false},
        {"title": "Address", "name":"addr"},
        {"title": "VRF/BD", "name":"vnid_name", "sortable": false}, //"sort_name":"first_learn.vnid_name"},
        {"title": "EPG", "name":"epg_name", "sortable":false}
    ]
    headers.forEach(function(h){
        self.table.headers.push(new gHeader(h))
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
    self.table.url("/api/ept/move")
    var headers = [
        {"title": "Time", "name":"ts_str", "sortable":false},
        {"title": "Fabric", "name":"fabric", "sortable": false},
        {"title": "Count", "name":"count", "sorted":true},
        {"title": "Type", "name":"type", "sortable": false},
        {"title": "Address", "name":"addr"},
        {"title": "VRF/BD", "name":"vnid_name", "sortable": false} //"sort_name":"first_learn.vnid_name"},
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


function common_viewModel() {
    var self = this; 
    self.isLoading = ko.observable(false)
    self.view = ko.observable("index")
    self.table = new gTable()
    self.fabrics = ko.observableArray([])
    self.current_fabric_name = ko.observable("")
    self.current_fabric = null

    //refresh fabric state and trigger provided callback on once full refresh has completed
    self.refresh_fabrics = function(success, fab){
        if(success===undefined){ success = function(){}}
        if(fab===undefined){ fab = null}
        var inflight = 0
        var check_all_complete = function(){
            inflight--
            if(inflight==0){success()}
        }
        json_get("/api/fabric?include=fabric&sort=fabric", function(data){
            var fabrics = []
            self.current_fabric = null
            data.objects.forEach(function(elem){
                var f = new fabric(elem.fabric.fabric)
                fabrics.push(f)
                if(self.current_fabric_name()==f.fabric()){
                    self.current_fabric = f
                }
                //support for refreshing a single fabric
                //if single fab was provided for refresh, then only trigger refresh for that fabric
                if(fab==null || f.fabric()==fab){
                    inflight++
                    f.refresh(check_all_complete)
                }
            })
            self.fabrics(fabrics)
            //possible that no fabrics where found or filtered fabric does not exists, in which 
            //case we need to trigger success function as there are no inflight requests
            if(inflight==0){success()}
        })
    }

    // set active class for active dashboard tab
    self.dashboard_active_tab = function(tab){
        if(self.view()==tab){ return "active" }
        return ""
    }

    // view functions 
    self.init = function(){
        self.isLoading(false);
        self.table.init()
    }
    self.view_dashboard_fabric = function(){
        self.init()
        self.view("dashboard_fabric")
        view_dashboard_fabric(self)
    }
    self.view_dashboard_fabric_events = function(args){
        self.init()
        self.view("dashboard_fabric_events")
        self.current_fabric_name(args[0])
        view_dashboard_fabric_events(self)
    }
    self.view_dashboard_endpoints = function(){
        self.init()
        self.view("dashboard_endpoints")
        view_dashboard_endpoints(self)
    }
    self.view_dashboard_moves = function(){
        self.init()
        self.view("dashboard_moves")
        view_dashboard_moves(self)
    }
    self.view_dashboard_offsubnet = function(){
        self.init()
        self.view("dashboard_offsubnet")
    }
    self.view_dashboard_stale = function(){
        self.init()
        self.view("dashboard_stale")
    }
    self.view_dashboard_rapid = function(){
        self.init()
        self.view("dashboard_rapid")
    }
    self.view_dashboard_remediate = function(){
        self.init()
        self.view("dashboard_remediate")
    }
    self.view_dashboard_events = function(){
        self.init()
        self.view("dashboard_events")
    }

    // simple same-page routing to support direct anchor links (very basic/static)
    // for now, just /case-# and /case-#/filename-#
    var routes = [
        {"route": "/fb-([^ \?&]+)/history", "view": self.view_dashboard_fabric_events},
        {"route": "/endpoints", "view": self.view_dashboard_endpoints},
        {"route": "/moves", "view": self.view_dashboard_moves},
        {"route": "/offsubnet", "view": self.view_dashboard_offsubnet},
        {"route": "/stale", "view": self.view_dashboard_stale},
        {"route": "/rapid", "view": self.view_dashboard_rapid},
        {"route": "/remediate", "view": self.view_dashboard_remediate},
        {"route": "/events", "view": self.view_dashboard_events},
    ]
    self.navigate = function(){
        for (var i in routes) {
            var r = routes[i]
            var regex = new RegExp("^#"+r["route"]+"$")
            var match = regex.exec(window.top.location.hash)
            if (match != null){
                if(match.length>1){
                    return r["view"](match.slice(1, match.length));
                }else{
                    return r["view"]();
                }
            }
        }
        return self.view_dashboard_fabric();
    }

    // searchbar handler (if present)
    self.searchBar = null;
    self.init_searchbar = function(){
        //destroy any existing select2 anchored on searchBar
        if(self.searchBar != null){
            try{$("#searchBar").select2("destroy")}catch(err){}
        }
        self.searchBar = $("#searchBar").select2({
            allowClear: true,
            placeholder: "Search MAC or IP address, 00:50:56:01:BB:12, 10.1.1.101, or 2001:A:B:C:D:65",
            ajax: {
                url: "http://esc-aci-compute:9080/api/ept/endpoint",
                //url: "/api/decode",
                dataType: 'json',
                delay: 250,
                data: function (params) {
                    return {
                        "filter": 'regex("addr","'+escapeRegExp(params.term).toUpperCase()+'")',
                        "include": "fabric,addr,vnid,type,first_learn",
                        "page-size": "20",
                        "sort": "addr",
                        "page": params.page
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
                            obj.dn = "/ept/fabric-"+obj.fabric+"/vnid-"+obj.vnid+"/addr-"+obj.addr
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
}

var page_vm
$().ready(function(){
    var self = new common_viewModel();
    page_vm = self
    ko.applyBindings(self);
    $("main").css("display","block")

    //add listener for hash change
    $(window).on("hashchange", function(){self.navigate();})

    //initialize searchbar if present
    self.init_searchbar()

    //trigger navigation on load
    self.navigate()

})


