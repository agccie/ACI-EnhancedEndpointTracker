import {environment} from "../../environments/environment";

export class FabricObject {
    fabric: Fabric;
}

export class FabricList {
    count: number;
    objects: FabricObject[];

    public constructor() {
        this.count = 0;
        this.objects = [];
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

    constructor(fabric: string = '', apic_hostname: string = '', apic_username: string = '', apic_password: string = '', apic_cert: string = '', ssh_username: string = '', ssh_password: string = '', max_events: number = 5) {
        if (environment.app_mode) {
            this.apic_cert = '';
        } else {
            this.apic_cert = apic_cert;
        }
        this.apic_hostname = apic_hostname;
        this.apic_password = apic_password;
        this.apic_username = apic_username;
        this.fabric = fabric;
        this.max_events = max_events;
        this.ssh_password = ssh_password;
        this.ssh_username = ssh_username;
        this.status = 'stopped';
        this.mac = 0;
        this.ipv4 = 0;
        this.ipv6 = 0;
        this.uptime = 0;
    }
}
