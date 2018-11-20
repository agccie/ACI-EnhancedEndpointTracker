import {environment} from "../../environments/environment";

export class Fabric {
    apic_cert: string;
    apic_hostname: string;
    apic_password: string;
    apic_username: string;
    fabric: string;
    max_events: number;
    ssh_password: string;
    ssh_username: string;

    constructor() {
        if (environment.app_mode) {
            this.apic_cert = '';
        }
        this.apic_hostname = '';
        this.apic_password = '';
        this.apic_username = '';
        this.fabric = '';
        this.max_events = 0;
        this.ssh_password = '';
        this.ssh_username = '';
    }
}
