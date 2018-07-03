

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

function fabricNodeLC(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"events": generalEvent}
    self.events = ko.observableArray([])
    self.max_events = ko.observable(0)
    self.event_count = ko.observable(0)
    self.lc_id = ko.observable(0)
    self.model = ko.observable("")
    self.status = ko.observable("")
    self.modTs = ko.observable("")
    self.pokes = ko.observable(0)
}

function fabricNode(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"events": generalEvent, "linecards": fabricNodeLC}
    self.isLoading = ko.observable(false)
    self.fabric = ko.observable("")
    self.node_id = ko.observable("")
    self.pod_id = ko.observable("")
    self.role = ko.observable("")
    self.name = ko.observable("")
    self.model = ko.observable("")
    self.status = ko.observable("")
    self.modTs = ko.observable("")
    self.events = ko.observableArray([])
    self.max_events = ko.observable(0)
    self.event_count = ko.observable(0)
    self.linecards = ko.observableArray([])

    //sum of event_count and all linecard event_count
    self.total_events = ko.computed(function(){
        var count = self.event_count()
        self.linecards().forEach(function(lc){
            count+=lc.event_count()
        })
        return count
    })
    
    //sum of linecard corrected count
    self.pokes = ko.computed(function(){
        var count=0
        self.linecards().forEach(function(lc){
            count+=lc.pokes()
        })
        return count
    })

    //manually execute workaround check
    self.ondemand_verify = function(){
        var url="/api/aci/nodes/"+self.fabric()+"/"+self.node_id()+"/verify"
        self.isLoading(true)
        json_post(url, data={}, function(data){
            //always returns success with 200 message
            self.isLoading(false)
            page_vm.fabric.get_nodes()
        })
    }

    //use alertmodal to show all events
    self.show_events = function(){
        console.log("show events")
        var html=""
            html+=  "<h5>Chassis "+self.node_id()+" "+self.model()+"</h5>" +
                    "<div class='timeline'>"+
                        "<div class='timeline__list'>"
            self.events().forEach(function(e){
                html+=      "<div class='timeline__item'>" +
                                '<div class="timeline__icon" ></div>' +
                                '<div class="timeline__time" >'+e.ts()+'</div>' +
                                '<div class="timeline__content">'     +
                                    '<div>'+e.description()+'</div>'  +
                                '</div>' +
                            "</div>"
            })
            html+=      "</div>"
            html+=  "</div>"
        self.linecards().forEach(function(lc){
            console.log(lc)
            html+=  "<h5>Linecard "+lc.lc_id()+" "+lc.model()+"</h5>" +
                    "<div class='timeline'>"+
                        "<div class='timeline__list'>"
            lc.events().forEach(function(e){
                html+=      "<div class='timeline__item'>" +
                                '<div class="timeline__icon" ></div>' +
                                '<div class="timeline__time" >'+e.ts()+'</div>' +
                                '<div class="timeline__content">'     +
                                    '<div>'+e.description()+'</div>'  +
                                '</div>' +
                            "</div>"
            })
            html+=      "</div>"
            html+=  "</div>"
        })    
        showInfoModal(html,html=true)
    }
}

function fabric(){
    baseModelObject.call(this)
    var self = this
    self._subtypes = {"events": generalEvent, "nodes": fabricNode}
    self.isLoading = ko.observable(false)
    self.formLoading = ko.observable(false)
    self.nodesLoading = ko.observable(false)
    self.init = ko.observable(false)
    self.fabric = ko.observable("")
    self.status = ko.observable("uknown")
    self.apic_cert = ko.observable("")
    self.apic_hostname = ko.observable("")
    self.apic_username = ko.observable("")
    self.apic_password = ko.observable("")
    self.ssh_username = ko.observable("")
    self.ssh_password = ko.observable("")
    self.max_events = ko.observable(0)
    self.event_count = ko.observable(0)
    self.events = ko.observableArray()
    self.nodes = ko.observableArray()
    self.node_ids = ko.observableArray()    // list of nodeIds only
   
    // boolean whether currently running
    self.status_running = ko.computed(function(){return self.status()=="Running"})

    // create/update fabric
    self.save = function(){
        var url="/api/aci/fabrics"
        var fabric_keys = [
            "fabric", "apic_hostname",
            "apic_username","apic_password","apic_cert",
            "ssh_username", "ssh_password"
        ]     
        var data={}
        var js=self.toJS()
        fabric_keys.forEach(function(key){
            if(key in js && js[key].length>0){
                data[key]=js[key]
            }
        })
        var method
        if(self.init()){
            //if fabric was initialized then this is an update
            url+="/"+self.fabric()
            method = json_patch
        }else{
            //else we are created new fabric
            method = json_post
        }
        self.formLoading(true)
        method(url, data, function(data){
            //verify configured credentials
            self.init(true)
            var url="/api/aci/fabrics/"+self.fabric()+"/verify"
            json_post(url, data={}, function(data){
                self.formLoading(false)
                if(data.success){
                    hideModal()
                    self.refresh_state()
                }else{
                    var err="verify credentials failed"
                    if(data.apic_error.length>0){ err=data.apic_error }
                    else if(data.switch_error.length>0){ err=data.switch_error}
                    showAlertModal(err)
                }
            })
        })
    }

    // start fabric monitor
    self.start = function(){
        var url="/api/aci/fabrics/"+self.fabric()+"/start"
        self.isLoading(true)
        json_post(url, data={}, function(data){
            self.isLoading(false)
            if(data.success){
                self.refresh_state()
            }else{
                if("error" in data){showAlertModal(data.error)}
                else{showAlertModal("start monitor failed")}
            }
        })
    }

    // stop fabric monitor
    self.stop = function(){
        var url="/api/aci/fabrics/"+self.fabric()+"/stop"
        self.isLoading(true)
        json_post(url, data={}, function(data){
            self.isLoading(false)
            if(data.success){
                self.refresh_state()
            }else{
                if("error" in data){showAlertModal(data.error)}
                else{showAlertModal("start monitor failed")}
            }
        })
    }

    //get fabric status 
    self.get_status = function(){
        self.isLoading(true)
        var url="/api/aci/fabrics/"+self.fabric()+"/status"
        json_get(url, function(data){
            self.isLoading(false)
            if("status" in data){ 
                self.status(data["status"].charAt(0).toUpperCase()+data["status"].substr(1))
            }
        })
    }

    //get fabric nodes status
    self.get_nodes = function(){
        self.nodesLoading(true)
        var url="/api/aci/nodes?fitler=eq('fabric','"+self.fabric()+"')&sort=node_id"
        json_get(url, function(data){
            var nodes = []
            var node_ids = []
            data["objects"].forEach(function(obj){
                var n = new fabricNode()
                n.fromJS(obj)
                //we only care about the spines
                if(n.role()=="spine"){
                    nodes.push(n)
                    node_ids.push(n.node_id())
                }
            })
            self.nodes(nodes)
            self.node_ids(node_ids)
            //now we need to get LC info and create object to push to each node
            var url="/api/aci/nodes/linecards?fitler=eq('fabric','"+self.fabric()+"')&sort=lc_id"
            json_get(url, function(data){
                self.nodesLoading(false)
                
                data["objects"].forEach(function(obj){
                    //self.nodes and self.node_ids are parallel arrays so should always 
                    //have fabricNode object in self.nodes that correlates to node_id in self.node_ids
                    var i = self.node_ids().indexOf(obj.node_id)
                    if(i>=0 && i<self.nodes().length){
                        var node=self.nodes()[i]
                        var lc = new fabricNodeLC()
                        lc.fromJS(obj)
                        node.linecards.push(lc)
                    }
                })
            })
        })
    }

    //refresh full state
    self.refresh_state = function(){
        var url="/api/aci/fabrics/"+self.fabric()
        self.isLoading(true)
        json_get(url, function(data){
            self.isLoading(false)
            if("objects" in data && data.objects.length>0){
                self.fromJS(data.objects[0])
            }
            self.get_status()
            self.get_nodes()
        })
    }
}

function common_viewModel() {
    var self = this; 
    self.isLoading = ko.observable(false);
    self.fabric = new fabric()
    self.show_fabric_events = ko.observable(false);

    //only support one fabric
    self.read_fabrics = function(){
        self.isLoading(true)
        var url="/api/aci/fabrics?include=fabric"
        json_get(url, function(data){
            self.isLoading(false);
            if("objects" in data && data.objects.length>0){
                self.fabric.fabric(data.objects[0].fabric)
                self.fabric.init(true)
                self.fabric.refresh_state()
            }
        })
    }

    //toggle fabric monitor events
    self.toggle_fabric_events = function(){
        self.show_fabric_events(!self.show_fabric_events())
    }

}

var page_vm
$().ready(function(){
    var self = new common_viewModel();
    page_vm = self
    ko.applyBindings(self);
    $("main").css("display","block")

    //load model and build select2 searchBar 
    self.isLoading(true);
    self.read_fabrics();
})
