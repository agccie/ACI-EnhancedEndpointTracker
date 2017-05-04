
/* SHARED VARIABLES */
var aci_vendor = "Cisco"
var aci_appId = "EnhancedEndpointTracker"
var aci_app = false

// basic object for mapping value to name
var valueName = function(value,name){
    this.value = value;
    this.name = name;
};

// user role's
ROLE_FULL_ADMIN     = 0
ROLE_USER           = 1
ROLE_BLACKLIST      = 2
ROLE_TYPES          = [0, 1, 2]
function role_to_name(type){
    switch(type){
        case ROLE_FULL_ADMIN    : return "Administrator";
        case ROLE_USER          : return "User";
        case ROLE_BLACKLIST     : return "Blacklist";
        default                 : return "Unknown type("+type+")";
    }
}

// logging levels
LEVEL_EMERGENCY     = 0
LEVEL_ALERT         = 1
LEVEL_CRITICAL      = 2
LEVEL_ERROR         = 3
LEVEL_WARN          = 4
LEVEL_NOTIFY        = 5
LEVEL_INFO          = 6
LEVLE_DEBUG         = 7

// build array of role options based off ROLE_TYPES array
var roleOptions = Array();
for(var i=0; i<ROLE_TYPES.length; i++){
    roleOptions.push(new valueName(ROLE_TYPES[i], role_to_name(ROLE_TYPES[i])));
}

/**
* fadeVisible
* custom knockout binding using jqueries fadeIn/fadeOut
*/
ko.bindingHandlers.fadeVisible = {
    init: function(element, valueAccessor) {
        // Start visible/invisible according to initial value
        var shouldDisplay = valueAccessor();
        $(element).toggle(shouldDisplay);
    },
    update: function(element, valueAccessor) {
        // On update, fade in/out
        var shouldDisplay = valueAccessor();
        shouldDisplay ? $(element).fadeIn() : $(element).fadeOut();
    } 
};

/**
* loadingWhen
* custom knockout binding to display loader while isLoading flag is set
* (dependent on jquery)
* https://github.com/stevegreatrex/ko.plus
*/
ko.bindingHandlers.loadingWhen = {
    init: function (element) {
        var 
            $element = $(element),
            currentPosition = $element.css("position")
            $loader = $("<div>").addClass("loader").hide();

        //add the loader
        $element.append($loader);
        
        //make sure that we can absolutely position the loader against the original element
        if (currentPosition == "auto" || currentPosition == "static")
            $element.css("position", "relative");

        //center the loader
        $loader.css({
            position: "absolute",
            top: "50%",
            left: "50%",
            "margin-left": -($loader.width() / 2) + "px",
            "margin-top": -($loader.height() / 2) + "px"
        });
    },
    update: function (element, valueAccessor) {
        var isLoading = ko.utils.unwrapObservable(valueAccessor()),
            $element = $(element),
            $childrenToHide = $element.children(":not(div.loader)"),
            $loader = $element.find("div.loader");

        if (isLoading) {
            $childrenToHide.css("visibility", "hidden").attr("disabled", "disabled");
            $loader.show();
        }
        else {
            $loader.fadeOut("fast");
            $childrenToHide.css("visibility", "visible").removeAttr("disabled");
        }
    }
};


/**
* perform JSON ajax get
*/
function json_get(url, func){
    if(aci_app){
        var turl = "/appcenter/"+aci_vendor+"/"+aci_appId+"/proxy.json?url="+url
        var headers = {
            "DevCookie": Cookies.get("app_"+aci_vendor+"_"+aci_appId+"_token"),
            "APIC-Challenge": Cookies.get("app_"+aci_vendor+"_"+aci_appId+"_urlToken")
        }
    }else{
        var turl = url
        var headers = {}
    }
    return $.ajax({
        url:turl,
        type:"GET",
        contentType:"application/json; charset=utf-8",
        dataType:"json",
        success: func,
        headers: headers
    })
}

/**
* perform true JSON ajax post (converts data object to json string)
*/ 
function json_post(url, data, func){
    if(aci_app){
        var turl = "/appcenter/"+aci_vendor+"/"+aci_appId+"/proxy.json"
        var tdata = {
            "url": url,
            "method": "post",
            "data": data
        }
        var headers = {
            "DevCookie": Cookies.get("app_"+aci_vendor+"_"+aci_appId+"_token"),
            "APIC-Challenge": Cookies.get("app_"+aci_vendor+"_"+aci_appId+"_urlToken")
        }
    }else{
        var turl = url
        var tdata = data
        var headers = {}
    }
    return $.ajax({
        url:turl,
        type:"POST",
        data: ko.toJSON(tdata),
        contentType:"application/json; charset=utf-8",
        dataType:"json",
        success: func,
        headers: headers
    });
}

/**
* perform true JSON ajax delete (converts data object to json string)
*/ 
function json_delete(url, data, func){
    if(aci_app){
        var turl = "/appcenter/"+aci_vendor+"/"+aci_appId+"/proxy.json"
        var tdata = {
            "url": url,
            "method": "delete",
            "data": data
        }
        var method = "POST"
        var headers = {
            "DevCookie": Cookies.get("app_"+aci_vendor+"_"+aci_appId+"_token"),
            "APIC-Challenge": Cookies.get("app_"+aci_vendor+"_"+aci_appId+"_urlToken")
        }
    }else{
        var turl = url
        var tdata = data
        var method = "DELETE"
        var headers = {}
    }
    return $.ajax({
        url:turl,
        type: method,
        data: ko.toJSON(tdata),
        contentType:"application/json; charset=utf-8",
        dataType:"json",
        success: func,
        headers: headers
    });
}

//get url parameter
//http://www.jquerybyexample.net/2012/06/get-url-parameters-using-jquery.html
function get_url_param(sParam){
    var sPageURL = window.location.search.substring(1);
    var sURLVariables = sPageURL.split('&');
    for (var i = 0; i < sURLVariables.length; i++)
    {
        var sParameterName = sURLVariables[i].split('=');
        if (sParameterName[0] == sParam)
        {
            if(typeof(sParameterName[1])=="undefined"){return "";}
            return sParameterName[1];
        }
    }
    //parameter not found
    return "";
}

//create error html with an XHR error object
function get_error_html(err, url){
    var status_code = "";
    var err_message = "";
    if(err.hasOwnProperty("status")){ status_code = err.status; }
    if(err.hasOwnProperty("responseJSON") && err.responseJSON.hasOwnProperty("error")){
        err_message = err.responseJSON.error;
    }else if(err.hasOwnProperty("statusText")){
        err_message = err.statusText;
    }else{
        err_message = "An unexpected error occurred."
    }
    if(aci_app && (status_code == 400 || status_code == 403)){
        err_message+="<br><br>This error generally indicates a session timeout on the APIC"
    }
    if(typeof url == 'undefined'){ url = ""; }
    else{
        url = " <span class=\"label label-info\">url: "+url+"</span>"
    }     
    code = "<span class=\"label label-danger\"><strong>Error "+status_code+"</strong></span>"
    return "<p>"+code+url+"</p><p>"+err_message+"</p>";
}

//general loading html
function get_loading_html(msg){
    if(typeof(msg) === "undefined"){ msg = "Loading"; }
    if(aci_app){
        return "<h4><img src=\"./static/img/loader.gif\"/> "+msg+"...</h4>"
    }
    return "<h4><img src=\"/static/img/loader.gif\"/> "+msg+"...</h4>"
}

//general confirmation html
function get_confirm_html(msg){
    var s = "<div><h3><span class=\"label label-danger\">Wait!</span></h3> ";
    s+= msg+"</div>";
    return s
}

//return html for confirm delete prompt
function get_confirm_delete_html(name){
    return get_confirm_html("Are you sure you want to delete \""+name+"\"?");
}

//define global timezoneOffset instead of calculating each call
tzoffset = -(new Date()).getTimezoneOffset()
function timestamp_to_string(ts){
    return moment(ts*1000).format('YYYY-MM-DD HH:mm:ss Z');
}

/**
* user object
*/
function user(){
    var self = this;
    self.id             = ko.observable(0);
    self.username       = ko.observable("");
    self.role           = ko.observable(0);
    self.role_name      = ko.observable("");
    self.last_login     = ko.observable("")
    //create this object from a server JSON object
    self.fromJS = function(obj){
        for (var key in obj) {
            if(obj.hasOwnProperty(key) && self.hasOwnProperty(key)){
                self[key](obj[key]);
            }
        }
        self.role_name(role_to_name(self.role()));
        //manually update id to indicate valid user (since model no longer
        //users id but JS uses it to determine new vs. existing user)
        self.id(1)
    };
    //nice timestamp display
    self.last_login_string = ko.computed(function(){
        if(self.last_login() == 0){ return "-"; }
        return timestamp_to_string(self.last_login())
    });
}

// convert node or vPC-node-pair to a string
function nodeToString(node){
    node = String(node)
    if(node.length>0){
        var iremote = parseInt(node)
        if(iremote>0x10000 && iremote<0xffffffff){
            var n1 = (iremote & 0xffff0000) >> 16
            var n2 = (iremote & 0x0000ffff)
            return (n1<n2)?"("+n1+","+n2+")":"("+n2+","+n1+")"
        }else if(node==0){
            return "deleted"
        }else{
            return ""+iremote
        }
    }else{
        return "-";
    }
}

// eptSetting 
function eptSetting(){
    var self = this;
    self.fabric = ko.observable("");
    self.apic_hostname = ko.observable("");
    self.apic_username = ko.observable("");
    self.apic_password = ko.observable("");
    self.apic_cert     = ko.observable("");
    self.ssh_username = ko.observable("");
    self.ssh_password = ko.observable("");
    self.ssh_access_method = ko.observable("");
    self.email_address = ko.observable("");
    self.syslog_server = ko.observable("");
    self.syslog_port = ko.observable(514);
    self.notify_move_email = ko.observable(true);
    self.notify_move_syslog = ko.observable(true);
    self.notify_stale_email = ko.observable(true);
    self.notify_stale_syslog = ko.observable(true);
    self.notify_offsubnet_email = ko.observable(true);
    self.notify_offsubnet_syslog = ko.observable(true);
    self.auto_clear_stale = ko.observable(false);
    self.auto_clear_offsubnet = ko.observable(false);
    self.analyze_move = ko.observable(true);
    self.analyze_stale = ko.observable(true);
    self.max_ep_events = ko.observable(64);
    self.max_jobs = ko.observable(65536);
    self.max_workers = ko.observable(6);
    self.processes = ko.observable(-1);  // running state of pariticular fabric
    self.count_mac = ko.observable("0"); // number of macs in this fabric's history
    self.count_ip = ko.observable("0");  // number of ip's in this fabric's history
    self.fabric_warning = ko.observable("");
    self.fabric_events = ko.observableArray();  
    self.fabric_events_count = ko.observable("0");

    //jsonify-able attributes
    self.attributes = [
        "fabric", "apic_hostname", "apic_username", "apic_password", "apic_cert",
        "ssh_username", "ssh_password","ssh_access_method",
        "email_address", "syslog_server", "syslog_port", 
        "notify_move_email", "notify_move_syslog", 
        "notify_stale_email", "notify_stale_syslog",
        "notify_offsubnet_email", "notify_offsubnet_syslog",
        "analyze_move", "analyze_stale", "analyze_offsubnet",
        "auto_clear_stale", "auto_clear_offsubnet"
    ]

    //return json containing this objects current attributes
    self.toPost = function(){
        var js = {}
        for (var i in self.attributes) {
            var key = self.attributes[i]
            if(self.hasOwnProperty(key)){ 
                var val = self[key]();
                if (typeof val == 'string' || val instanceof String){
                    //don't update if key length is 0 for passwords
                    if(val.length==0 && (key == "apic_password" || key == "ssh_password")){ continue; }
                    else{ js[key] = val; }
                }else{ 
                    js[key] = val;
                }
            }
        }   
        return js;
    }


    //create this object from a server JSON object
    self.fromJS = function(obj){
        for (var key in obj) {
            if(obj.hasOwnProperty(key) && self.hasOwnProperty(key)){
                self[key](obj[key]);
            }
        }
    };

    self.s_status = ko.computed(function(){
        var process_count = self.processes()
        if(process_count<0){ return "-";}
        else if(process_count==0){ return "Stopped";}
        // most recent event in fabric_events is actual status
        else if(self.fabric_events().length>0){
            return self.fabric_events()[0]["status"]
        }
        return "-"
    });
    self.s_status_description = ko.computed(function(){
        if(self.fabric_events().length>0){
            return self.fabric_events()[0]["description"];
        }
        return ""
    });
    self.s_status_time = ko.computed(function(){
        if(self.fabric_events().length>0){
            return timestamp_to_string(self.fabric_events()[0]["ts"]);
        }
        return ""
    });
    self.css_status = ko.computed(function(){
        var process_count = self.processes()
        if(process_count<=0){ return "label label-default";}
        else if(process_count==1){ return "label label-warning";}
        else{ return "label label-success";}
    });
    self.css_fabric_warning = ko.computed(function(){
        if(self.fabric_warning().length>0){ return "danger";}
        return "";
    });
}

// eptVpcNode
function eptVpcNode(){
    var self=this;
    self.id = ko.observable("")
    self.peerIp = ko.observable("")
    //create this object from a server JSON object
    self.fromJS = function(obj){
        for (var key in obj) {
            if(obj.hasOwnProperty(key) && self.hasOwnProperty(key)){
                self[key](obj[key]);
            }
        }
    };
}

// eptFabricNode
function eptFabricNode(){
    var self = this;
    self.fabric = ko.observable("");
    self.dn = ko.observable("");
    self.name = ko.observable("");
    self.oobMgmtAddr = ko.observable("");
    self.state = ko.observable("");
    self.role = ko.observable("");
    self.address = ko.observable("");
    self.systemUpTime = ko.observable("");
    self.id = ko.observable("");
    self.nodes = ko.observableArray();

    //create this object from a server JSON object
    self.fromJS = function(obj){
        for (var key in obj) {
            if(key=="nodes"){
                for(var i=0; i<obj.nodes.length; i++){
                    var l = new eptVpcNode();
                    l.fromJS(obj.nodes[i])
                    self.nodes.push(l);
                }       
            }
            else if(obj.hasOwnProperty(key) && self.hasOwnProperty(key)){
                self[key](obj[key]);
            }
        }
    };

    self.vpc_pair = ko.computed(function(){
        if(self.nodes().length > 0){
            var ta = []
            ko.utils.arrayForEach(self.nodes(), function(n){
                ta.push(n.id())
            })
            ta.sort()
            return "("+ta+")"
        }
        return "-"
    });

    self.css_role = ko.computed(function(){
        if(self.role() =="controller"){
            return "label label-primary"
        }
        else if(self.role() == "vpc"){
            return "label label-info"
        }
        return "label label-default"
    });
}

// eptFabricTunnel = tunnelIf
function eptFabricTunnel(){
    var self = this;
    self.dn = ko.observable("");
    self.fabric = ko.observable("");
    self.operSt = ko.observable("");
    self.dest = ko.observable("");
    self.src = ko.observable("");
    self.tType = ko.observable("");
    self.type = ko.observable("");
    self.node = ko.observable("");
    self.id = ko.observable("");

    //create this object from a server JSON object
    self.fromJS = function(obj){
        for (var key in obj) {
            if(obj.hasOwnProperty(key) && self.hasOwnProperty(key)){
                self[key](obj[key]);
            }
        }
    };

    self.type_str = ko.computed(function(){
        return self.tType()+","+self.type()
    })
    self.css_status = ko.computed(function(){
        if(self.operSt()=="up"){ return "label label-success";}
        return "label label-danger";
    })
}

// eptTop
function eptTop(){
    var self = this;
    self.status = ko.observable("");
    self.fabric = ko.observable("");
    self.addr = ko.observable("");
    self.count = ko.observable("");
    self.ts = ko.observable("");
    self.type = ko.observable("");
    self.vnid = ko.observable("");
    self.node = ko.observable("");
    self.vnid_name = ko.observable("");

    //create this object from a server JSON object
    self.fromJS = function(obj){
        for (var key in obj) {
            if(obj.hasOwnProperty(key) && self.hasOwnProperty(key)){
                self[key](obj[key]);
            }
        }
    };

    self.endpoint_url = ko.computed(function(){
        if(aci_app){
            var ep = "/"+self.fabric()+"/"+self.vnid()+"/"+self.addr()
            return "/apps/"+aci_vendor+"_"+aci_appId+"/UIAssets/endpoints.html?ep="+ep
        }
        return "/ept/"+self.fabric()+"/"+self.vnid()+"/"+self.addr()
    });
    self.move_url = ko.computed(function(){
        return "/ept/moves/"+self.fabric()+"/"+self.vnid()+"/"+self.addr()
    });
    self.s_ts = ko.computed(function(){
        if(self.ts().length==0){return "-";}     
        return timestamp_to_string(self.ts());
    });
    self.s_vnid = ko.computed(function(){
        //console.log(self.vnid()+","+self.addr()+" => "+self.vnid_name());
        if(self.vnid_name().length>0){ return self.vnid_name()}
        return "vnid: "+self.vnid()
    });
    self.s_node = ko.computed(function(){
        return nodeToString(self.node());
    });
    self.css_type = ko.computed(function(){
        if(self.type()=="mac"){ return "label label-warning"; }
        return "label label-primary";
    });
   self.css_status = ko.computed(function(){
        if(self.status()=="deleted"){
            return "label label-danger";
        }
        else if(self.status()=="modified"){
            return "label label-default";
        }
        else{ return "label label-info"; }
    });
}

// eptHistoryCount
function eptHistoryCount(){
    var self = this;
    self.fabric = ko.observable("");
    self.ip = ko.observable("");
    self.mac = ko.observable("");

    //create this object from a server JSON object
    self.fromJS = function(obj){
        for (var key in obj) {
            if(obj.hasOwnProperty(key) && self.hasOwnProperty(key)){
                self[key](obj[key]);
            }
        }
    };
}

// eptHistory
function eptHistory(){
    var self = this;
    self.status = ko.observable("");
    self.dn = ko.observable("");
    self.node = ko.observable("");
    self.addr = ko.observable("");
    self.type = ko.observable("");
    self.createTs = ko.observable("");
    self.ts = ko.observable("");
    self.pcTag = ko.observable("");
    self.flags = ko.observable("");
    self.vrf = ko.observable("");
    self.bd = ko.observable("");
    self.encap = ko.observable("");
    self.remote = ko.observable("");
    self.ifId = ko.observable("");
    self.rw_mac = ko.observable("");
    self.rw_bd = ko.observable("");
    self.epg_name = ko.observable("");
    self.vnid_name = ko.observable("");

    //create this object from a server JSON object
    self.fromJS = function(obj){
        for (var key in obj) {
            if(obj.hasOwnProperty(key) && self.hasOwnProperty(key)){
                self[key](obj[key]);
            }
        }
    };

    self.css_status = ko.computed(function(){
        if(self.status()=="deleted"){
            return "label label-danger";
        }
        else if(self.status()=="modified"){
            return "label label-default";
        }
        else{ return "label label-info"; }
    });

    self.s_ts = ko.computed(function(){
        if(self.ts().length==0){return "-";}     
        return timestamp_to_string(self.ts());
    });
    self.s_node = ko.computed(function(){
        return nodeToString(self.node())
    });
    self.remote_node = ko.computed(function(){
        return nodeToString(self.remote())
    });
    self.s_createTs = ko.computed(function(){
        if(self.createTs().length==0){ return "-"; }
        return self.createTs();
    });
    self.s_epg = ko.computed(function(){
        if(self.epg_name().length==0){return "-";}
        return self.epg_name();
    });
    self.s_ifId = ko.computed(function(){
        if(self.ifId().length==0 || self.status()=="deleted"){ return "-";}
        return self.ifId();
    });      
    self.s_encap = ko.computed(function(){
        if(self.encap().length==0 || self.status()=="deleted"){ return "-";}
        return self.encap();
    });
    self.s_pcTag = ko.computed(function(){
        if(self.pcTag().length==0 || self.status()=="deleted"){ return "-";}
        else if(self.pcTag()=="any"){ return "-";}
        return self.pcTag();
    });
    self.s_flags = ko.computed(function(){
        if(self.flags().length==0 || self.status()=="deleted"){ return "-";}
        return self.flags();
    });
    self.s_rw_bd = ko.computed(function(){
        if(self.rw_bd().length==0 || self.status()=="deleted"){ return "-";}
        return self.rw_bd()
    });
    self.css_rw_bd = ko.computed(function(){
        if(self.rw_bd().length==0 || self.status()=="deleted"){ return "";}
        return "label label-default"
    });
    self.s_rw_mac = ko.computed(function(){
        if(self.rw_mac().length==0){ return "-";}
        return self.rw_mac()
    });
    self.css_rw_mac = ko.computed(function(){
        //if(self.rw_mac().length==0){ return "";}
        //return "label label-warning"
        return ""
    });
    self.is_mac = ko.computed(function(){
        if(self.type()=="mac"){return true;}
        return false;
    });
    self.css_type = ko.computed(function(){
        //if(self.is_mac()){return "label label-warning"}
        //return "label label-primary"
        return ""
    })

}

// eptMove
function eptMove(){
    var self = this;
    var fields = ["encap","flags","ifId","node","pcTag","rw_bd","rw_mac","ts", 
                    "epg_name", "vnid_name"]
    self.dst = {}
    self.src = {}
    for (var key in fields){
        self.src[fields[key]] = ko.observable("");
        self.dst[fields[key]] = ko.observable("");
    }

    //create this object from a server JSON object
    self.fromJS = function(obj){
        var dtypes = ["src", "dst"]
        for(var i=0; i<dtypes.length; i++){
            var d = dtypes[i]
            if(obj.hasOwnProperty(d)){
                for (var key in obj[d]){
                    if(obj[d].hasOwnProperty(key) && self[d].hasOwnProperty(key)){
                        self[d][key](obj[d][key]);
                    }
                }
            }
        }   
    };

    //general string value for attribute
    var general = function(obj){
        if(obj.length==0){ return "-";}
        else if(obj == "any"){ return "-";}
        else{ return ""+obj; }
    }
    self.diff = function(attr){
       if(self.src.hasOwnProperty(attr) && self.dst.hasOwnProperty(attr) &&
            self.src[attr]().length>0 && self.dst[attr]().length>0 && 
            self.src[attr]()!=self.dst[attr]()){
            return "warning";
        }
        return "";
    };
    self.s_ts = ko.computed(function(){
        if(self.dst.ts().length==0){return "-";}     
        return timestamp_to_string(self.dst.ts());
    });
    self.s_src_node = ko.computed(function(){
        return nodeToString(self.src.node());
    });
    self.s_dst_node = ko.computed(function(){
        return nodeToString(self.dst.node());
    });
    self.s_src_ifId = ko.computed(function(){
        return general(self.src.ifId())
    });
    self.s_dst_ifId = ko.computed(function(){
        return general(self.dst.ifId())
    });

    self.s_src_encap = ko.computed(function(){return general(self.src.encap());});
    self.s_dst_encap = ko.computed(function(){return general(self.dst.encap());});
    self.s_src_pcTag = ko.computed(function(){return general(self.src.pcTag());});
    self.s_dst_pcTag = ko.computed(function(){return general(self.dst.pcTag());});
    self.s_src_rw_bd = ko.computed(function(){return general(self.src.rw_bd());});
    self.s_dst_rw_bd = ko.computed(function(){return general(self.dst.rw_bd());});
    self.s_src_rw_mac = ko.computed(function(){return general(self.src.rw_mac());});
    self.s_dst_rw_mac = ko.computed(function(){return general(self.dst.rw_mac());});
    self.s_src_epg = ko.computed(function(){return general(self.src.epg_name())});
    self.s_dst_epg = ko.computed(function(){return general(self.dst.epg_name())});

    self.css_src_rw_bd = ko.computed(function(){
        if(self.src.rw_mac().length==0){ return "";}
        return "label label-default"
    });
    self.css_dst_rw_bd = ko.computed(function(){
        if(self.dst.rw_mac().length==0){ return "";}
        return "label label-default"
    });
    self.css_src_rw_mac = ko.computed(function(){
        //if(self.src.rw_mac().length==0){ return "";}
        //return "label label-warning"
        return ""
    });
    self.css_dst_rw_mac = ko.computed(function(){
        //if(self.dst.rw_mac().length==0){ return "";}
        //return "label label-warning"
        return ""
    });

    // string description of what changed for a move
    self.move_description = ko.computed(function(){
        var compare_order = ["rw_mac", "epg_name", "node", "ifId", "pcTag", "encap", "rw_bd"];
        var qualifier = null;
        for(var i=0; i<compare_order.length; i++){
            var q = compare_order[i];
            //only compare if both values are set (else we don't know if they match)
            if(self.src[q]().length==0 || self.dst[q]().length==0){ continue; }
            //skip pcTag if 'any'
            if(q=="pcTag"){
                if(self.src.pcTag()=="any" || self.dst.pcTag()=="any"){
                    continue;
                }
            }
            if(self.src[q]()!=self.dst[q]()){
                qualifier = q;
                break;
            }
        }
        if(qualifier!=null){
            var s = self.src[qualifier]()
            var d = self.dst[qualifier]()
            var q = qualifier
            switch(qualifier){
                case "node":    s = self.s_src_node(); 
                                d = self.s_dst_node();
                                break;
                case "ifId":    s = self.s_src_ifId();
                                d = self.s_dst_ifId(); 
                                q = "interface";
                                break;
                case "pcTag":   s = self.s_src_pcTag(); 
                                d = self.s_dst_pcTag();
                                break;
                case "encap":   s = self.s_src_encap(); 
                                d = self.s_dst_encap(); 
                                break;
                case "rw_bd":   s = self.s_src_rw_bd();
                                d = self.s_dst_rw_bd(); 
                                q = "Bd";
                                break;
                case "rw_mac":  s = self.s_src_rw_mac();
                                d = self.s_dst_rw_mac();
                                q = "Mac";
                                break;
                case "epg_name":s = self.s_src_epg()
                                d = self.s_dst_epg()
                                q = "EPG";
                                break;
            }
            return q+" changed from "+s+" to "+d
        }
        //didn't find anything different, prevent full state
        return "" + self.s_src_node()+","+self.s_src_ifId()+","+self.s_src_pcTag()+","+
                    self.s_src_encap()+","+self.s_src_rw_bd()+","+self.s_src_rw_mac()+" to "+
                    self.s_dst_node()+","+self.s_dst_ifId()+","+self.s_dst_pcTag()+","+
                    self.s_dst_encap()+","+self.s_dst_rw_bd()+","+self.s_dst_rw_mac()
                    
    });
}

// eptStale
function eptStale(){
    var self = this;
    self.node = ko.observable("");  // node with stale entry
    self.remote = ko.observable("");
    self.expected_remote = ko.observable("");
    self.ts = ko.observable("");
    self.pcTag = ko.observable("");
    self.flags = ko.observable("");
    self.encap = ko.observable("");
    self.ifId = ko.observable("");
    self.rw_mac = ko.observable("");
    self.rw_bd = ko.observable("");
    self.epg_name = ko.observable("");
    self.vnid_name = ko.observable("");

    //create this object from a server JSON object
    self.fromJS = function(obj){
        for (var key in obj) {
            if(obj.hasOwnProperty(key) && self.hasOwnProperty(key)){
                self[key](obj[key]);
            }
        }
    };

    //general string value for attribute
    var general = function(obj){
        if(obj.length==0){ return "-";}
        else if(obj == "any"){ return "-";}
        else{ return ""+obj; }
    }

    self.s_pcTag = ko.computed(function(){return general(self.pcTag());});
    self.s_flags = ko.computed(function(){return general(self.flags());});
    self.s_encap = ko.computed(function(){return general(self.encap());});
    self.s_ifId = ko.computed(function(){return general(self.ifId());});
    self.s_rw_bd = ko.computed(function(){return general(self.rw_bd());});
    self.s_rw_mac = ko.computed(function(){return general(self.rw_mac());});

    self.s_remote = ko.computed(function(){return nodeToString(self.remote())});
    self.s_expected_remote = ko.computed(function(){
        return nodeToString(self.expected_remote())
    });
    self.s_epg = ko.computed(function(){
        if(self.epg_name().length==0){return "-";}
        return self.epg_name();
    });

    self.s_ts = ko.computed(function(){
        if(self.ts().length==0){return "-";}     
        return timestamp_to_string(self.ts());
    });

    self.css_rw_bd = ko.computed(function(){
        if(self.rw_bd().length==0){ return "";}
        return "label label-default"
    });
    self.css_rw_mac = ko.computed(function(){
        //if(self.rw_mac().length==0){ return "";}
        //return "label label-warning"
        return ""
    });

}

/**
* listen for token objects from parent frame when running as aci app
* success and error functions can be provided for proper action to take
*/
function appTokenRefresh(success, error){
    if(success === undefined){
        //no-op on success by default
        success = function(){}
    }
    if(error === undefined){
        //no-op on error by default
        error = function(e){}
    }
    window.addEventListener("message", function(e){
        //if(e.source === window.parent){
        if(true){
            try{
                var tokenObj =  JSON.parse(e.data);
                if(!tokenObj.hasOwnProperty("appId") || !tokenObj.hasOwnProperty("urlToken") ||
                    !tokenObj.hasOwnProperty("token")){
                    var err = {"statusText":"Token missing one or more required attributes: "}
                    err.statusText+="appId, token, urlToken"
                    error(err)
                    return
                }
                Cookies.set("app_"+tokenObj.appId+"_token", tokenObj.token);            
                Cookies.set("app_"+tokenObj.appId+"_urlToken", tokenObj.urlToken);            
                window.APIC_DEV_COOKIE = tokenObj.token
                window.APIC_URL_TOKEN = tokenObj.urlToken
                console.log("setting token: "+ tokenObj.token+", urlToken: "+tokenObj.urlToken)
                success()
            } catch(e) {
                var err = {"statusText":"Cannot load token from backend"}
                console.log("error occurred: "+e)
                error(err)
            }
        }
    });
}

/**
* poll app_started api continuously until app has successfully started
* execute success callback.  If an error occurs, just keep polling
*/
pollAppTimeout = 3000;
function pollAppStarted(success){
    if(success === undefined){
        //no-op on success by default
        success = function(){}
    }
    checkAppStarted(function(){return success();}, function(){
        var d = new Date()
        console.log(d+" app has not yet started, recheck in "+pollAppTimeout+"ms");
        setTimeout(function(){ pollAppStarted(success) }, pollAppTimeout);
    }).error(function(err){
        var d = new Date()
        console.log(d+" an error occurred polling AppStarted: "+err+", recheck in "+pollAppTimeout+"ms")
        setTimeout(function(){ pollAppStarted(success) }, pollAppTimeout);
    });
}
/**
* check if app has started.  Accepts 'success' and 'fail' functions
*/
function checkAppStarted(success, fail){
    var url = "/api/ept/app_started"
    if(success === undefined){
        //no-op on success by default
        success = function(){}
    }
    if(fail === undefined){
        //no-op on fail by default
        fail = function(){}
    }
    return json_get(url, function(data){
        if(data.started){ 
            var d = new Date();
            console.log(d+" app has started");
            return success();
        }
        else{ return fail();}
    });
}
