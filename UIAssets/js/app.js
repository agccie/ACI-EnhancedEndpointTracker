
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
        {"title": "Fabric", "name":"fabric"},
        {"title": "Type", "name":"type"},
        {"title": "Address", "name":"addr", "sorted":true, "sort_direction":"asc"},
        {"title": "VRF/BD", "name":"vnid_name" , "sort_name":"first_learn.vnid_name"}, 
        {"title": "EPG", "name":"epg_name", "sort_name":"events.0.epg_name"}
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
        {"title": "Time", "name":"ts_str", "sort_name":"events.0.dst.ts"},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Count", "name":"count", "sorted":true},
        {"title": "Type", "name":"type"},
        {"title": "Address", "name":"addr"},
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
    self.table.url("/api/ept/offsubnet")
    var headers = [
        {"title": "Time", "name":"ts_str", "sort_name":"events.0.ts", "sorted":true},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Node", "name":"node"},
        {"title": "Type", "name":"type"},
        {"title": "Address", "name":"addr"},
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
    self.table.url("/api/ept/stale")
    var headers = [
        {"title": "Time", "name":"ts_str", "sort_name":"events.0.ts", "sorted":true},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Node", "name":"node"},
        {"title": "Type", "name":"type"},
        {"title": "Address", "name":"addr"},
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
    self.table.url("/api/ept/history")
    var headers = [
        {"title": "Time", "name":"ts_str", "sort_name":"events.0.ts", "sorted":true},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Node", "name":"node"},
        {"title": "Status", "name":"status_str", "sort_name":"events.0.status"},
        {"title": "Address", "name":"addr"},
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
    self.table.url("/api/ept/rapid")
    var headers = [
        {"title": "Time", "name":"ts_str", "sort_name":"events.ts", "sorted":true},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Event Rate (per minute)", "name":"rate", "sort_name":"events.rate"},
        {"title": "Type", "name":"type"},
        {"title": "Address", "name":"addr"},
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
    self.table.url("/api/ept/remediate")
    var headers = [
        {"title": "Time", "name":"ts_str", "sort_name":"events.ts", "sorted":true},
        {"title": "Fabric", "name":"fabric"},
        {"title": "Node", "name":"node"},
        {"title": "Address", "name":"addr"},
        {"title": "Action", "name":"action", "sortable":false},
        {"title": "Reason", "name":"reason", "sortable":false},
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

function common_viewModel() {
    var self = this; 
    self.isLoading = ko.observable(false)
    self.view = ko.observable("index")
    self.table = new gTable()
    self.fabrics = ko.observableArray([])
    self.current_fabric_name = ko.observable("")
    self.current_fabric = null
    self.historical_tab = ko.observable(false)

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
        self.isLoading(false)
        self.historical_tab(false)
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
        self.historical_tab(true)
        view_dashboard_offsubnet(self)
    }
    self.view_dashboard_stale = function(){
        self.init()
        self.historical_tab(true)
        self.view("dashboard_stale")
        view_dashboard_stale(self)
    }
    self.view_dashboard_rapid = function(){
        self.init()
        self.historical_tab(true)
        self.view("dashboard_rapid")
        view_dashboard_rapid(self)
    }
    self.view_dashboard_remediate = function(){
        self.init()
        self.view("dashboard_remediate")
        view_dashboard_remediate(self)
    }
    self.view_dashboard_latest_events = function(){
        self.init()
        self.view("dashboard_latest_events")
        view_dashboard_latest_events(self)
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
        {"route": "/events", "view": self.view_dashboard_latest_events},
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


