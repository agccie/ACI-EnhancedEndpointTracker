export class EndpointObject {
    'ept.endpoint': Endpoint;
    'ept.stale': Endpoint;
    'ept.offsubnet': Endpoint;
    'ept.history': Endpoint;
    'ept.rapid': Endpoint;
}

export class EndpointList {
    count: number;
    objects: EndpointObject[];

    public constructor(data) {
        this.count = 0;
        this.objects = [];
        if ("count" in data) {
            this.count = data["count"];
        }
        if ("objects" in data) {
            for (const ept of data["objects"]) {
                this.objects.push(ept[Object.keys(ept)[0]]);
            }
        }
    }
}

export class Endpoint {
    addr: any;
    addr_byte: any;
    count: any;
    dn: any;
    events: any;
    fabric: any;
    first_learn: any;
    is_offsubnet: any;
    is_rapid: any;
    is_rapid_ts: any;
    is_stale: any;
    rapid_count: any;
    rapid_icount: any;
    rapid_lcount: any;
    rapid_lts: any;
    type: any;
    vnid: any;
    node: any;

    constructor(addr: any, addr_byte: any, count: any, dn: any, events: any, fabric: any, first_learn: any,
                is_offsubnet: any, is_rapid: any, is_rapid_ts: any, is_stale: any, rapid_count: any, rapid_icount: any,
                rapid_lcount: any, rapid_lts: any, type: any, vnid: any, node: any) {
        this.addr = addr;
        this.addr_byte = addr_byte;
        this.count = count;
        this.dn = dn;
        this.events = events;
        this.fabric = fabric;
        this.first_learn = first_learn;
        this.is_offsubnet = is_offsubnet;
        this.is_rapid = is_rapid;
        this.is_rapid_ts = is_rapid_ts;
        this.is_stale = is_stale;
        this.rapid_count = rapid_count;
        this.rapid_icount = rapid_icount;
        this.rapid_lcount = rapid_lcount;
        this.rapid_lts = rapid_lts;
        this.type = type;
        this.vnid = vnid;
        this.node = node;
    }
}
