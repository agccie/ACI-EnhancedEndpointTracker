export class FabricList {
    count: number;
    objects: Fabric[];

    public constructor(data) {
        this.count = 0;
        this.objects = [];
        if ("count" in data) {
            this.count = data["count"];
        }
        if ("objects" in data) {
            data["objects"].forEach(obj => {
                if ('fabric' in obj) {
                    this.objects.push(new Fabric(obj['fabric']));
                }
            });
        }
    }
}

export class FabricEvent {
    description: string = '-';
    status: string = '-';
    timestamp: number = 0;
    
    constructor(data: any = {}) {
        this.init();
        this.sync(data);
    }

    //initialize or re-initialize all attributes to default values
    init() {
        this.description = '-';
        this.status = '-';
        this.timestamp = 0;
    }

    // sync Fabric object to provided JSON
    sync(data: any = {}) {
        for (let attr in data) {
            if (attr in this) {
                if(typeof(data[attr])==="string" && data[attr].length==0){
                    continue;
                }
                this[attr] = data[attr];
            }
        }
    }
}

export class Fabric {
    apic_cert: string;
    apic_hostname: string;
    apic_password: string;
    apic_username: string;
    fabric: string;
    max_events: number;
    ssh_password: string;
    ssh_username: string;
    session_timeout: number;
    subscription_refresh_time: number;
    status: string;
    display_status: string;
    mac: number;
    ipv4: number;
    ipv6: number;
    events: FabricEvent[];
    uptime: number;
    heartbeat_interval: number;
    heartbeat_max_retries: number;
    heartbeat_timeout: number;

    constructor(data: any = {}) {
        this.init();
        this.sync(data);
    }

    //initialize or re-initialize all attributes to default values
    init() {
        this.apic_hostname = '';
        this.apic_username = '';
        this.apic_password = '';
        this.apic_cert = '';
        this.fabric = '';
        this.max_events = 0;
        this.ssh_password = '';
        this.ssh_username = '';
        this.session_timeout = 0;
        this.subscription_refresh_time = 0;
        this.heartbeat_interval = 0;
        this.heartbeat_max_retries = 0;
        this.heartbeat_timeout = 0;
        this.status = 'stopped';
        this.display_status = 'stopped';
        this.events = [];
        this.mac = 0;
        this.ipv4 = 0;
        this.ipv6 = 0;
        this.uptime = 0;
    }

    // sync Fabric object to provided JSON
    sync(data: any = {}) {
        for (let attr in data) {
            if(attr == "events"){
                if(Array.isArray(data.events)){
                    let events = [];
                    data.events.forEach(function(elem){
                        events.push(new FabricEvent(elem));
                    });
                    this.events = events;
                }
            }
            else if (attr in this) {
                this[attr] = data[attr];
            }
        }
    }

    // set the status attribute which also triggers update to display_status attribute
    set_status(status:string, ) {
        this.status = status;
        if(this.status == 'running' && this.events.length>0){
            this.display_status = this.events[0].status;
        } else {
            this.display_status == this.status;
        }
    }

    // for UI, we want fabric create to only be fabric name as that is only attribute customer
    // will provide on create independent of default values
    get_create_json(): object {
        let json = {};
        json["fabric"] = this.fabric;
        return json;
    }

    // not all attributes of this object are used for create/update operatons, this function
    // will return a JSON object with writeable attributes only. Additionally, only attributes
    // that are set (non-emptry string) are returned.
    get_save_json(): object {
        let attr = [
            "fabric",
            "apic_hostname",
            "apic_password",
            "apic_username",
            "apic_cert",
            "max_events",
            "ssh_username",
            "ssh_password",
            "session_timeout",
            "subscription_refresh_time",
            "heartbeat_interval",
            "heartbeat_max_retries",
            "heartbeat_timeout"
        ];
        let json = {};
        for (let i = 0; i < attr.length; i++) {
            let a = attr[i];
            if (a in this) {
                if ((typeof this[a] === 'string' && this[a].length == 0)|| 
                    (typeof this[a] === 'number' && this[a]==0)) {
                    //skip string attributes that are not set with exception of heartbeat_interval
                    if(a != "heartbeat_interval"){
                        continue;
                    }
                }
                json[a] = this[a];
            } else {
                console.log("unknown fabricSettings attribute to save: " + a);
            }
        }
        return json;
    }
}