export class FabricSettings {
    analyze_move: boolean;
    analyze_offsubnet: boolean;
    analyze_stale: boolean;
    auto_clear_offsubnet: boolean;
    auto_clear_stale: boolean;
    dn: string;
    email_address: string;
    fabric: string;
    max_endpoint_events: number;
    max_per_node_endpoint_events: number;
    notify_move_email: boolean;
    notify_move_syslog: boolean;
    notify_offsubnet_email: boolean;
    notify_offsubnet_syslog: boolean;
    notify_stale_email: boolean;
    notify_stale_syslog: boolean;
    queue_init_epm_events: boolean;
    queue_init_events: boolean;
    settings: string;
    stale_multiple_local: boolean;
    stale_no_local: boolean;
    syslog_port: number;
    syslog_server: string;

    constructor() {
        this.analyze_move = false;
        this.analyze_offsubnet = false;
        this.analyze_stale = false;
        this.auto_clear_offsubnet = false;
        this.auto_clear_stale = false;
        this.dn = '';
        this.email_address = '';
        this.fabric = '';
        this.max_endpoint_events = 0;
        this.max_per_node_endpoint_events = 0;
        this.notify_move_email = false;
        this.notify_move_syslog = false;
        this.notify_offsubnet_email = false;
        this.notify_offsubnet_syslog = false;
        this.notify_stale_email = false;
        this.notify_stale_syslog = false;
        this.queue_init_epm_events = false;
        this.queue_init_events = false;
        this.settings = '';
        this.stale_multiple_local = false;
        this.stale_no_local = false;
        this.syslog_port = 0;
        this.syslog_server = '';

    }
}
