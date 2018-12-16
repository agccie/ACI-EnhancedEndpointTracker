export class FabricSettingsList {
    count: number;
    objects: FabricSettings[];

    public constructor(data) {
        this.count = 0;
        this.objects = [];
        if ("count" in data) {
            this.count = data["count"];
        }
        if ("objects" in data) {
            for (const obj of data["objects"]) {
                if ('ept.settings' in obj) {
                    this.objects.push(new FabricSettings(obj['ept.settings']));
                }
            }
        }
    }
}

export class FabricSettings {
    fabric: string;
    settings: string;
    analyze_move: boolean;
    analyze_offsubnet: boolean;
    analyze_stale: boolean;
    analyze_rapid: boolean;
    auto_clear_offsubnet: boolean;
    auto_clear_stale: boolean;
    email_address: string;
    max_endpoint_events: number;
    max_per_node_endpoint_events: number;
    notify_move_email: boolean;
    notify_move_syslog: boolean;
    notify_offsubnet_email: boolean;
    notify_offsubnet_syslog: boolean;
    notify_stale_email: boolean;
    notify_stale_syslog: boolean;
    notify_rapid_email: boolean;
    notify_rapid_syslog: boolean;
    notify_clear_email: boolean;
    notify_clear_syslog: boolean;
    queue_init_epm_events: boolean;
    queue_init_events: boolean;
    rapid_holdtime: number;
    rapid_threshold: number;
    refresh_rapid: boolean;
    stale_multiple_local: boolean;
    stale_no_local: boolean;
    syslog_port: number;
    syslog_server: string;

    constructor(data: any = {}) {
        this.init();
        this.sync(data);
    }

    //initialize or re-initialize all attributes to default values
    init() {
        this.fabric = '';
        this.settings = 'default';
        this.analyze_move = false;
        this.analyze_offsubnet = false;
        this.analyze_stale = false;
        this.analyze_rapid = false;
        this.auto_clear_offsubnet = false;
        this.auto_clear_stale = false;
        this.email_address = '';
        this.max_endpoint_events = 0;
        this.max_per_node_endpoint_events = 0;
        this.notify_move_email = false;
        this.notify_move_syslog = false;
        this.notify_offsubnet_email = false;
        this.notify_offsubnet_syslog = false;
        this.notify_stale_email = false;
        this.notify_stale_syslog = false;
        this.notify_rapid_email = false;
        this.notify_rapid_syslog = false;
        this.notify_clear_email = false;
        this.notify_clear_syslog = false;
        this.queue_init_epm_events = false;
        this.queue_init_events = false;
        this.rapid_holdtime = 0;
        this.rapid_threshold = 0;
        this.refresh_rapid = false;
        this.stale_multiple_local = false;
        this.stale_no_local = false;
        this.syslog_port = 0;
        this.syslog_server = '';
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
    // will return a JSON object with writeable attributes only
    get_save_json(): object {
        let attr = [
            "analyze_move",
            "analyze_offsubnet",
            "analyze_stale",
            "analyze_rapid",
            "auto_clear_offsubnet",
            "auto_clear_stale",
            "email_address",
            "max_endpoint_events",
            "max_per_node_endpoint_events",
            "notify_move_email",
            "notify_move_syslog",
            "notify_offsubnet_email",
            "notify_offsubnet_syslog",
            "notify_stale_email",
            "notify_stale_syslog",
            "notify_rapid_email",
            "notify_rapid_syslog",
            "notify_clear_email",
            "notify_clear_syslog",
            "queue_init_epm_events",
            "queue_init_events",
            "rapid_holdtime",
            "rapid_threshold",
            "refresh_rapid",
            "stale_multiple_local",
            "stale_no_local",
            "syslog_port",
            "syslog_server",
        ];
        let json = {};
        for (let i = 0; i < attr.length; i++) {
            let a = attr[i];
            if (a in this) {
                json[a] = this[a];
            } else {
                console.log("unknown fabricSettings attribute to save: " + a);
            }
        }
        return json;
    }
}
