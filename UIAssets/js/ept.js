
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
    self.analyze_move = ko.observable(true)
    self.analyze_offsubnet = ko.observable(true)
    self.analyze_stale = ko.observable(true)
    self.analyze_rapid = ko.observable(true)
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
    self.max_events = ko.observable(0)
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
    self.refresh = function(user_success){
        if(user_success===undefined){ user_success = function(){}}
        var success = function(){
            // always perform status check last
            self.loading_status(true)
            json_get(base+"/status", function(data){
                self.status(data.status)
                self.loading_status(false)
                return user_success(self)
            })
        }
        self.loading_fabric(true)
        self.loading_settings(true)
        self.loading_count_mac(true)
        self.loading_count_ipv4(true)
        self.loading_count_ipv6(true)
        var base = "/api/uni/fb-"+self.fabric()
        var count_base = "/api/ept/endpoint?count=1&filter=and(eq(\"fabric\",\""+self.fabric()+"\"),neq(\"events.0.status\",\"deleted\"),"
        json_get(base, function(data){
            if(data.objects.length>0){
                self.fromJS(data.objects[0].fabric)
            }
            self.loading_fabric(false)
            if(!self.isLoading()){success(self)}
        })
        json_get(base+"/settings-default", function(data){
            if(data.objects.length>0){
                self.settings.fromJS(data.objects[0]["ept.settings"])
            }
            self.loading_settings(false)
            if(!self.isLoading()){success(self)}
        })
        json_get(count_base+"eq(\"type\",\"mac\"))", function(data){
            self.count_mac(data.count)
            self.loading_count_mac(false)
            if(!self.isLoading()){success(self)}
        })
        json_get(count_base+"eq(\"type\",\"ipv4\"))", function(data){
            self.count_ipv4(data.count)
            self.loading_count_ipv4(false)
            if(!self.isLoading()){success(self)}
        })
        json_get(count_base+"eq(\"type\",\"ipv6\"))", function(data){
            self.count_ipv6(data.count)
            self.loading_count_ipv6(false)
            if(!self.isLoading()){success(self)}
        })
    }
}

// general event used by eptEndpoint, eptHistory, eptStale, etc...
function generalEvent(){
    baseModelObject.call(this)
    var self = this
    self.fabric = ko.observable("")     // embedded from parent classname for endpoint detail
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
    self.expected_remote = ko.observable(0)
    self.classname = ko.observable("")
    self.flags = ko.observableArray([])
    self.ts_str = ko.computed(function(){
        return timestamp_to_string(self.ts())
    }) 
    self.node_str = ko.computed(function(){
        if(self.node()==0){ return "-" }
        return vpc_node_string(self.node())
    })
    self.remote_str = ko.computed(function(){
        if(self.remote()==0){ return "-" }
        return vpc_node_string(self.remote())
    })
    self.expected_remote_str = ko.computed(function(){
        if(self.expected_remote()==0){ return "-" }
        return vpc_node_string(self.expected_remote())
    })
    self.pctag_str = ko.computed(function(){
        if(self.pctag()==0){ return "-" }
        return self.pctag()
    })
    self.flags_str = ko.computed(function(){
        if(self.flags().length==0){ return "-" }
        return self.flags().join(",")
    })
    self.mac_str = ko.computed(function(){
        if(self.rw_mac().length==0){ return "-" }
        return self.rw_mac()
    })
    self.encap_str = ko.computed(function(){
        if(self.encap().length==0){ return "-" }
        return self.encap()
    })
    self.epg_name_str = ko.computed(function(){
        if(self.epg_name().length==0){ return "-" }
        return self.epg_name()
    })
    self.is_deleted = ko.computed(function(){
        return self.status()=="deleted"
    })
    // custom cell formatting per attribute
    self.formatter = function(attr, text){
        if(attr == "status"){
            return '<span class="'+get_status_label(text)+'">'+text+'</span>'
        } else if (attr == "mac_str") {
            if(self.rw_mac().length>0 && self.rw_bd()>0){
                var url = '#/fb-'+self.fabric()+'/vnid-'+self.rw_bd()+'/addr-'+self.rw_mac()
                return '<a href="'+url+'">'+text+'</a>'
            }
        }
        return text
    }
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
    // pulled from eptHistory, list of nodes currently offsubnet or stale
    self.stale_nodes = ko.observableArray([])
    self.offsubnet_nodes = ko.observableArray([])
    //determine if endpoint is deleted from fabric
    self.is_deleted = ko.computed(function(){
        if(self.events().length>0 && self.events()[0].status()!="deleted"){
            return false
        }
        return true
    })
    //rapid timestampe
    self.is_rapid_ts_str = ko.computed(function(){
        return timestamp_to_string(self.is_rapid_ts())
    }) 
    // various flags highlight a problem with this endpoint and needs to set danger css
    self.is_danger = ko.computed(function(){
        return (self.is_stale() || self.is_offsubnet() || self.is_rapid())
    })
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
            return '<span class="'+get_endpoint_type_label(text)+'">'+text+'</span>'
        }
        else if(attr == "addr"){
            var url = '#/fb-'+self.fabric()+'/vnid-'+self.vnid()+'/addr-'+self.addr()
            return '<a href="'+url+'">'+text+'</a>'
        }
        else if(attr == "state"){
            // need to have labels for active/deleted/offsubnet/stale/rapid
            var state=""
            if(self.is_deleted()){
                state+='<span class="'+get_status_label("deleted")+'">inactive</span>'
            } else {
                state+='<span class="'+get_status_label("created")+'">active</span>'
            }
            if(self.is_offsubnet()){
                state+='<span class="label label--danger">offsubnet</span>'
            }
            if(self.is_stale()){
                state+='<span class="label label--danger">stale</span>'
            }
            if(self.is_rapid()){
                state+='<span class="label label--danger">rapid</span>'
            }
            return state
        }
        return text
    }
    self.blockquote_css = ko.computed(function(){
        //if(self.is_danger()){return "blockquote--danger"}
        return get_endpoint_type_blockquote(self.type())
    })
    self.type_css = ko.computed(function(){
        //if(self.is_danger()){ return "label label--danger"}
        return get_endpoint_type_label(self.type())
    })
    self.addr_css = ko.computed(function(){
        //if(self.is_danger()){ return "text-danger"}
        return get_endpoint_type_text(self.type())
    })
    self.vnid_identifier = ko.computed(function(){
        if(self.vnid_name().length==0){ return "vnid" }
        else if(self.type()=="mac"){ return "BD" }
        return "VRF"
    })
    self.vnid_value = ko.computed(function(){
        if(self.vnid_name().length>0){ return self.vnid_name() }
        return self.vnid()
    })
    // local info
    self.local_node = ko.computed(function(){
        if(self.is_deleted()){ return "-" }
        return vpc_node_string(self.events()[0].node())
    })
    self.local_interface = ko.computed(function(){
        if(self.is_deleted()){ return "-" }
        return self.events()[0].intf_name() 
    })
    self.local_encap = ko.computed(function(){
        if(self.is_deleted()){ return "-" }
        return self.events()[0].encap()
    })
    self.local_mac = ko.computed(function(){
        if(self.is_deleted()){ return "-" }
        return self.events()[0].rw_mac()
    })
    self.local_mac_href = ko.computed(function(){
        if(self.is_deleted() || self.events()[0].rw_mac().length==0 || self.events()[0].rw_bd()==0){ 
            return "#" 
        }
        return "#/fb-"+self.fabric()+"/vnid-"+self.events()[0].rw_bd()+"/addr-"+self.events()[0].rw_mac()
    })
}

//return html for src/dst cell within move table
function moveWrapper(src, dst){
    if(src.length==0){ src = "&nbsp"; }
    if(dst.length==0){ dst = "&nbsp"; }
    return "<div>"+dst+"</div><div>"+src+"</div>"
}

function moveEvent(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"src": generalEvent, "dst":generalEvent }
    self.src = new generalEvent()
    self.dst = new generalEvent()
    self.fabric = ko.observable("")     // embedded from parent classname for endpoint detail
    self.direction = moveWrapper("src","dst")
    self.ts_str = ko.computed(function(){
        return self.dst.ts_str()
    })
    self.ts_move_str = ko.computed(function(){
        return moveWrapper("",self.ts_str())
    })
    self.node_str = ko.computed(function(){
        return moveWrapper(vpc_node_string(self.src.node()), vpc_node_string(self.dst.node())) 
    })
    self.intf_name = ko.computed(function(){
        return moveWrapper(self.src.intf_name(), self.dst.intf_name())
    })
    self.encap = ko.computed(function(){
        return moveWrapper(self.src.encap(), self.dst.encap())
    })
    self.epg_name = ko.computed(function(){
        return moveWrapper(self.src.epg_name_str(), self.dst.epg_name_str())
    })
    self.mac_str = ko.computed(function(){
        return moveWrapper(self.src.rw_mac(), self.dst.rw_mac())
    })
    // custom cell formatting per attribute
    self.formatter = function(attr, text){
        if (attr == "mac_str") {
            if(self.src.rw_mac().length>0 && self.src.rw_bd()>0){
                var url1 = '#/fb-'+self.fabric()+'/vnid-'+self.src.rw_bd()+'/addr-'+self.src.rw_mac()
                var url2 = '#/fb-'+self.fabric()+'/vnid-'+self.dst.rw_bd()+'/addr-'+self.dst.rw_mac()
                return moveWrapper(
                    '<a href="'+url1+'">'+self.src.rw_mac()+'</a>',
                    '<a href="'+url2+'">'+self.dst.rw_mac()+'</a>'
                )
            }
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
            return '<span class="'+get_endpoint_type_label(text)+'">'+text+'</span>'
        }
        else if(attr == "addr"){
            var url = '#/fb-'+self.fabric()+'/vnid-'+self.vnid()+'/addr-'+self.addr()+'/moves';
            return '<a href="'+url+'">'+text+'</a>'
        }
        return text
    }
}

function eptOffsubnet(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"events": generalEvent }
    self.fabric = ko.observable("")
    self.vnid = ko.observable(0)
    self.addr = ko.observable("")
    self.type = ko.observable("")
    self.node = ko.observable(0)
    self.events = ko.observableArray([])
    self.count = ko.observable(0)

    //get ts_str from first event
    self.ts_str = ko.computed(function(){
        if(self.events().length>0){ return self.events()[0].ts_str() }
        return "-"
    })

    // get vnid_name from events.0
    self.vnid_name = ko.computed(function(){
        var name = ""
        if(self.events().length>0 && self.events()[0].vnid_name().length>0){ 
            name = self.events()[0].vnid_name(); 
        }
        if(name.length>0){ return name }
        return "-"
    })
    // custom cell formatting per attribute
    self.formatter = function(attr, text){
        if(attr == "type"){
            return '<span class="'+get_endpoint_type_label(text)+'">'+text+'</span>'
        }
        else if(attr == "addr"){
            var url = '#/fb-'+self.fabric()+'/vnid-'+self.vnid()+'/addr-'+self.addr()+'/offsubnet';
            return '<a href="'+url+'">'+text+'</a>'
        }
        return text
    }
}

function eptStale(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"events": generalEvent }
    self.fabric = ko.observable("")
    self.vnid = ko.observable(0)
    self.addr = ko.observable("")
    self.type = ko.observable("")
    self.node = ko.observable(0)
    self.events = ko.observableArray([])
    self.count = ko.observable(0)

    //get ts_str from first event
    self.ts_str = ko.computed(function(){
        if(self.events().length>0){ return self.events()[0].ts_str() }
        return "-"
    })

    // get vnid_name from events.0
    self.vnid_name = ko.computed(function(){
        var name = ""
        if(self.events().length>0 && self.events()[0].vnid_name().length>0){ 
            name = self.events()[0].vnid_name(); 
        }
        if(name.length>0){ return name }
        return "-"
    })
    // custom cell formatting per attribute
    self.formatter = function(attr, text){
        if(attr == "type"){
            return '<span class="'+get_endpoint_type_label(text)+'">'+text+'</span>'
        }
        else if(attr == "addr"){
            var url = '#/fb-'+self.fabric()+'/vnid-'+self.vnid()+'/addr-'+self.addr()+'/stale';
            return '<a href="'+url+'">'+text+'</a>'
        }
        return text
    }
}

function eptHistory(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"events": generalEvent }
    self.fabric = ko.observable("")
    self.vnid = ko.observable(0)
    self.addr = ko.observable("")
    self.type = ko.observable("")
    self.node = ko.observable(0)
    self.is_stale = ko.observable(false)
    self.is_offsubnet = ko.observable(false)
    self.events = ko.observableArray([])
    self.count = ko.observable(0)

    //get ts_str from first event
    self.ts_str = ko.computed(function(){
        if(self.events().length>0){ return self.events()[0].ts_str() }
        return "-"
    })
    self.status_str = ko.computed(function(){
        if(self.events().length>0){ return self.events()[0].status() }
        return "-"
    })

    // get vnid_name from events.0
    self.vnid_name = ko.computed(function(){
        var name = ""
        if(self.events().length>0 && self.events()[0].vnid_name().length>0){ 
            name = self.events()[0].vnid_name(); 
        }
        if(name.length>0){ return name }
        return "-"
    })
    // custom cell formatting per attribute
    self.formatter = function(attr, text){
        if(attr == "type"){
            return '<span class="'+get_endpoint_type_label(text)+'">'+text+'</span>'
        }
        else if(attr == "addr"){
            var url = '#/fb-'+self.fabric()+'/vnid-'+self.vnid()+'/addr-'+self.addr()
            return '<a href="'+url+'">'+text+'</a>'
        }
        else if(attr == "status_str"){
            return '<span class="'+get_status_label(text)+'">'+text+'</span>'
        }
        return text
    }
}

// general event used by eptRapid
function rapidEvent(){
    baseModelObject.call(this)
    var self = this
    self.ts = ko.observable(0)
    self.vnid_name = ko.observable("")
    self.fabric = ko.observable("")     // embedded from parent classname for endpoint detail
    self.ts_str = ko.computed(function(){
        return timestamp_to_string(self.ts())
    }) 
    // endpoint count/rate when rapid was triggered
    self.rate = ko.observable(0)    
    self.count = ko.observable(0)   
    self.rate_str = ko.computed(function(){
        return parseInt(self.rate())
    })
}

function eptRapid(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"events": rapidEvent }
    self.fabric = ko.observable("")
    self.vnid = ko.observable(0)
    self.addr = ko.observable("")
    self.type = ko.observable("")
    self.events = ko.observableArray([])

    //get ts_str from first event
    self.ts_str = ko.computed(function(){
        if(self.events().length>0){ return self.events()[0].ts_str() }
        return "-"
    })
    // get rate from events.0
    self.rate = ko.computed(function(){
        if(self.events().length>0){ return parseInt(self.events()[0].rate()) }
        return "-"
    })
    // get count from events.0
    self.count_str = ko.computed(function(){
        if(self.events().length>0){ return parseInt(self.events()[0].count()) }
        return "-"
    })

    // get vnid_name from events.0
    self.vnid_name = ko.computed(function(){
        var name = ""
        if(self.events().length>0 && self.events()[0].vnid_name().length>0){ 
            name = self.events()[0].vnid_name(); 
        }
        if(name.length>0){ return name }
        return "-"
    })
    // custom cell formatting per attribute
    self.formatter = function(attr, text){
        if(attr == "type"){
            return '<span class="'+get_endpoint_type_label(text)+'">'+text+'</span>'
        }
        else if(attr == "addr"){
            var url = '#/fb-'+self.fabric()+'/vnid-'+self.vnid()+'/addr-'+self.addr()+'/rapid'
            return '<a href="'+url+'">'+text+'</a>'
        }
        return text
    }
}

// general event used by eptEndpoint, eptHistory, eptStale, etc...
function remediateEvent(){
    baseModelObject.call(this)
    var self = this
    self.fabric = ko.observable("")
    self.ts = ko.observable(0)
    self.ts_str = ko.computed(function(){
        return timestamp_to_string(self.ts())
    }) 
    self.action = ko.observable("")
    self.reason = ko.observable("")
    self.action_str = ko.computed(function(){
        if(self.action().length==0){ return "-" }
        return self.action()
    })
    self.reason_str = ko.computed(function(){
        if(self.reason().length==0){ return "-" }
        return self.reason()
    })
    //used to copy value from eptRemediate into event for table view
    self.node = ko.observable("")
}

function eptRemediate(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"events": remediateEvent }
    self.fabric = ko.observable("")
    self.vnid = ko.observable(0)
    self.addr = ko.observable("")
    self.type = ko.observable("")
    self.node = ko.observable(0)
    self.events = ko.observableArray([])
    self.count = ko.observable(0)

    //get ts_str from first event
    self.ts_str = ko.computed(function(){
        if(self.events().length>0){ return self.events()[0].ts_str() }
        return "-"
    })

    // get action/reason from events.0
    self.action = ko.computed(function(){
        if(self.events().length>0 && self.events()[0].action().length>0){ 
                return self.events()[0].action()
        }
        return "-"
    })
    // get action/reason from events.0
    self.reason = ko.computed(function(){
        if(self.events().length>0 && self.events()[0].reason().length>0){ 
                return self.events()[0].reason()
        }
        return "-"
    })

    // custom cell formatting per attribute
    self.formatter = function(attr, text){
        if(attr == "type"){
            return '<span class="'+get_endpoint_type_label(text)+'">'+text+'</span>'
        }
        else if(attr == "addr"){
            var url = '#/fb-'+self.fabric()+'/vnid-'+self.vnid()+'/addr-'+self.addr()+'/remediate';
            return '<a href="'+url+'">'+text+'</a>'
        }
        return text
    }
}


