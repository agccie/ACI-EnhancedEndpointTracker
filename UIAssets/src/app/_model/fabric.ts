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

export class Fabric {
    apic_cert: string;
    apic_hostname: string;
    apic_password: string;
    apic_username: string;
    fabric: string;
    max_events: number;
    ssh_password: string;
    ssh_username: string;
    status: string;
    mac: number;
    ipv4: number;
    ipv6: number;
    events: any[];
    uptime: number;

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
        this.status = 'stopped';
        this.events = [];
        this.mac = 0;
        this.ipv4 = 0;
        this.ipv6 = 0;
        this.uptime = 0;
    }

    // sync Fabric object to provided JSON
    sync(data: any = {}) {
        for (let attr in data) {
            if (attr in this) {
                this[attr] = data[attr];
            }
        }
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
            "ssh_password"
        ];
        let json = {};
        for (let i = 0; i < attr.length; i++) {
            let a = attr[i];
            if (a in this) {
                if ((typeof this[a] === 'string' && this[a].length == 0)|| 
                    (typeof this[a] === 'number' && this[a]==0)) {
                    //skip string attributes that are not set
                    continue;
                }
                json[a] = this[a];
            } else {
                console.log("unknown fabricSettings attribute to save: " + a);
            }
        }
        return json;
    }
}