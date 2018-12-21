
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
        this.is_active = false;
        this.is_ctrl = false;
        this.is_flagged = false;
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
        this.is_active = this.is_ctrl || this.is_flagged || (this.events.length>0 && this.events[0].status!="deleted");
    }
}

export class EndpointEvent {
    ts: number = 0;
    status: string = "";
    remote: number = 0;
    pctag: number = 0;
    flags: string[] = [];
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

    constructor(data: any = {}) {
        this.init();
        this.sync(data);
    }

    init() {
        this.ts = 0;
        this.status = "";
        this.remote = 0;
        this.pctag = 0;
        this.flags = [];
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
    }
    
    // sync EndpointEvent object to provided JSON
    sync(data: any = {}) {
        for (let attr in data) {
            if(attr in this){
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
