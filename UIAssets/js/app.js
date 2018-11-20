

function generalEvent(){
    baseModelObject.call(this)
    var self = this
    self.timestamp = ko.observable(0)
    self.status = ko.observable("")
    self.description = ko.observable("")
    self.ts = ko.computed(function(){
        return timestamp_to_string(self.timestamp())
    }) 
    self.timeline_status = ko.computed(function(){
        if(self.status()=="Starting"){ return "timeline--success";}
        else if(self.status()=="Stopping"){ return "timeline--warning";}
    })
}

function common_viewModel() {
    var self = this; 
    self.isLoading = ko.observable(false)
    self.welcomeLoading = ko.observable(false)
    self.view = ko.observable("welcome")

    // view functions 
    self.init = function(){
        self.isLoading(false);
    }
    self.view_index = function(){
        self.init()
        self.view("welcome")
    }

    // simple same-page routing to support direct anchor links (very basic/static)
    // for now, just /case-# and /case-#/filename-#
    var routes = [
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
        return self.view_index();
    }

    // forward user to selected object hash
    self.forward = function(route){
        if(route == null){
            window.top.location.hash = "/";
        }else{
            window.top.location.hash = route;
        }
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
            placeholder: "Search MAC or IP address, 00:50:56:01:BB:12, 10.1.1.101, or 2001:A::65",
            ajax: {
                url: "http://esc-aci-compute:9080/api/ept/endpoint",
                //url: "/api/decode",
                dataType: 'json',
                delay: 250,
                data: function (params) {
                    return {
                        "filter": 'regex("addr","'+params.term.toUpperCase()+'")',
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
                    return "Matched: "+data.count
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
                self.forward(evt.params.data.dn)
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
