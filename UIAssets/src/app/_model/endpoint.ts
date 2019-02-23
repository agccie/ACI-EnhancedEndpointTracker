
// receive an integer node and a list of nodes where one node is returned 
// if the value is <0xffff, else two nodes are returned representing a vpc pair
export function getLocalNodeList(value: number){
    if (value > 0xffff) {
        const nodeA = (value & 0xffff0000) >> 16;
        const nodeB = (value & 0x0000ffff);
        return [nodeA, nodeB];
    }
    return [value];
}

export function nodeToString(value: number, tunnelFlags:string[]=[]): string{
    let localNode = '-';
    if (value > 0xffff) {
        const nodeA = (value & 0xffff0000) >> 16;
        const nodeB = (value & 0x0000ffff);
        localNode = `(${nodeA},${nodeB})`;
    } else if (value === 0) {
        localNode = '-';
        //set localNode to proxy if 'proxy' set in any of the provided tunnel flags
        tunnelFlags.forEach(element =>{
            if(element.includes("proxy")){
                localNode=element;
            }
        })
    } else {
        localNode = ""+value;
    }
    return localNode;
}

export class EndpointList {
    count: number;
    objects: Endpoint[];

    public constructor(data) {
        const EndpointTypes = {
            "ept.endpoint": Endpoint,
            "ept.stale": Endpoint,
            "ept.offsubnet": Endpoint,
            "ept.history": Endpoint,
            "ept.rapid": Endpoint,
            "ept.remediate": Endpoint,
            "ept.move": EndpointMove,
        }
        
        this.count = 0;
        this.objects = [];
        if ("count" in data) {
            this.count = data["count"];
        }
        if ("objects" in data) {
            for (const obj of data["objects"]) {
                let obj_type = Object.keys(obj)[0]
                if(obj_type in EndpointTypes){
                    this.objects.push(new EndpointTypes[obj_type](obj[obj_type]));
                }
            }
        }
    }
}

export class EndpointMove {
    fabric: string = "";
    vnid: number = 0;
    addr: string = "";
    type: string = ""; 
    count: number = 0;
    events: EndpointMoveEvent[] = [];
    constructor(data: any = {}) {
        this.init();
        this.sync(data);
    }
    init(){
        this.fabric = "";
        this.vnid = 0;
        this.addr = "";
        this.type = "";
        this.count = 0;
        this.events = [];
    }
    // sync to provided JSON
    sync(data: any = {}) {
        for (let attr in data) {
            if(attr in this){
                if(attr == "events"){
                    if(Array.isArray(data.events)){
                        let events = [];
                        data.events.forEach(function(elem){
                            events.push(new EndpointMoveEvent(elem));
                        });
                        this.events = events;
                    }
                } else {
                    if ((typeof this[attr] === 'string' && data[attr].length == 0)|| 
                        (typeof this[attr] === 'number' && data[attr]==0)) {
                        //skip string attributes that are not set
                        continue;
                    }
                    this[attr] = data[attr];
                }
            }
        }
    }
}

export class EndpointMoveEvent {
    dst: EndpointEvent;
    src: EndpointEvent;
    constructor(data: any = {}) {
        this.init();
        this.sync(data);
    }
    init(){
        this.dst = new EndpointEvent();
        this.src = new EndpointEvent();
    }
    // sync EndpointMoveEvent object to provided JSON
    sync(data: any = {}) {
        for (let attr in data) {
            if(attr == "dst"){
                this.dst.sync(data[attr]);
            }
            else if(attr == "src"){
                this.src.sync(data[attr]);
            }
        }
    }
}

export class Endpoint {
    fabric: string = "";
    vnid: number = 0;
    node: number = 0;
    addr: string = "";
    type: string = "";
    learn_type: string = "";
    dn: string = "";
    count: number = 0;
    events: EndpointEvent[] = [];
    first_learn: EndpointEvent;
    is_offsubnet: boolean = false;
    is_stale: boolean = false;
    is_rapid: boolean = false;

    //auto-calculated after sync
    is_flagged: boolean = false;
    is_ctrl: boolean = false;   
    is_active: boolean = false;
    vnid_name: string = "-";
    epg_name: string = "-";
    is_local: boolean = false;
    local_node: number = 0;
    local_pod: number = 0;
    local_interface: string = "-";
    local_encap: string = "-";
    local_rw_mac: string = "-";
    local_rw_bd: number = 0;

    constructor(data: any = {}) {
        this.init();
        this.sync(data);
    }
    init() {
        this.fabric = "";
        this.vnid = 0;
        this.node = 0;
        this.addr = "";
        this.type = "";
        this.learn_type = "";
        this.dn = "";
        this.count = 0;
        this.events = [];
        this.first_learn = new EndpointEvent();
        this.is_offsubnet = false;
        this.is_stale = false;
        this.is_rapid = false;
        // dynamically calculated
        this.is_local = false;
        this.is_active = false;
        this.is_ctrl = false;
        this.is_flagged = false;
        this.vnid_name = "-";
        this.epg_name = "-";
        this.local_node = 0;
        this.local_pod = 0;
        this.local_encap = "-";
        this.local_rw_mac = "-";
        this.local_rw_bd = 0;
    }
    // sync Endpoint object to provided JSON
    sync(data: any = {}) {
        for (let attr in data) {
            if(attr == "events"){
                if(Array.isArray(data.events)){
                    let events = [];
                    data.events.forEach(function(elem){
                        events.push(new EndpointEvent(elem));
                    });
                    this.events = events;
                }
            } else if(attr == "first_learn"){
                this.first_learn.sync(data.first_learn);
            }
            else if (attr in this) {
                this[attr] = data[attr];
            }
        }

        //update calculated values
        this.is_flagged = this.is_rapid || this.is_offsubnet || this.is_stale;
        this.is_ctrl = !(this.learn_type.length==0 || this.learn_type=="epg" || this.learn_type=="external");
        this.is_active = this.is_ctrl || this.is_flagged || (this.events.length>0 && 
                                (this.events[0].status=="created"||this.events[0].status=="modified"));
        // set vnid name and epg name based of lastest event or first_learn of no events are present
        if(this.events.length>0){
            this.vnid_name = this.events[0].vnid_name;
            this.epg_name = this.events[0].epg_name;
            if(this.events[0].status=="created" || this.events[0].status=="modified"){
                this.is_local = true;
                this.local_pod = this.events[0].pod;
                this.local_node = this.events[0].node;
                this.local_interface = this.events[0].intf_name;
                this.local_encap = this.events[0].encap;
                if(this.type!="mac" && this.events[0].rw_bd>0){
                    this.local_rw_mac = this.events[0].rw_mac;
                    this.local_rw_bd = this.events[0].rw_bd;
                }
            }
        } else {
            this.vnid_name = this.first_learn.vnid_name;
            this.epg_name = this.first_learn.epg_name;
        }
    }
}

export class EndpointEvent {
    ts: number = 0;
    pod: number = 0;
    node: number = 0;
    status: string = "";
    remote: number = 0;
    expected_remote: number = 0;
    pctag: number = 0;
    flags: string[] = [];
    tunnel_flags: string[] = [];
    encap: string = "-";
    intf_name: string = "-";
    rw_mac: string = "";;
    rw_bd: number = 0;
    epg_name: string = "-";
    vnid_name: string = "-";
    // count and rate are used by ept.rapid only
    count: number = 0;
    rate: number = 0;
    // action and reason are used by ept.remediate only
    action: string = "-";
    reason: string = "-";
    // calculated strings
    flags_string: string = "-";
    node_string: string = "-";
    remote_string: string = "-";
    reporting_node: string = "-";

    constructor(data: any = {}) {
        this.init();
        this.sync(data);
    }

    init() {
        this.ts = 0;
        this.node = 0;
        this.pod = 0;
        this.status = "";
        this.remote = 0;
        this.expected_remote = 0;
        this.pctag = 0;
        this.flags = [];
        this.tunnel_flags = [];
        this.encap = "-";
        this.intf_name = "-";
        this.rw_mac = "";
        this.rw_bd = 0;
        this.epg_name = "-";
        this.vnid_name = "-";
        this.action = "-";
        this.reason = "-";
        this.count = 0;
        this.rate = 0;
        this.flags_string = "-";
        this.node_string = "-";
        this.remote_string = "-";
        this.reporting_node = "-";
    }
    
    // sync EndpointEvent object to provided JSON
    sync(data: any = {}) {
        for (let attr in data) {
            if(attr == "tunnel_flags"){
                //tunnel flags on backend is a comma-separated string, need to convert to list of strings
                if(data[attr].length>0){
                    this.tunnel_flags = data[attr].split(",")
                }
            }
            else if(attr in this){
                if ((typeof this[attr] === 'string' && data[attr].length == 0)|| 
                    (typeof this[attr] === 'number' && data[attr]==0)) {
                    //skip string attributes that are not set
                    continue;
                }
                this[attr] = data[attr];
            }
        }
        // force rate to integer
        this.rate = Math.floor(this.rate);
        if(this.flags.length>0){
            this.flags_string = this.flags.join(",")
        }
        if(this.node>0){
            this.reporting_node = "node-"+this.node;
            this.node_string = nodeToString(this.node, this.tunnel_flags);
        }
        this.remote_string = nodeToString(this.remote, this.tunnel_flags);
    }
}
