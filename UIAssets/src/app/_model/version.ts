export class Version {
    app_id: string = "";
    author: string = "";
    branch: string = "";
    commit: string = "";
    timestamp: number = 0;
    version: string = "";
    contact_url: string = "";
    contact_email: string = "";

    constructor(data: any = {}) {
        this.init();
        this.sync(data);
    }

    //initialize or re-initialize all attributes to default values
    init() {
        this.app_id = "";
        this.author = "";
        this.branch = "";
        this.commit = "";
        this.timestamp = 0;
        this.version = "";
        this.contact_url = "";
        this.contact_email = "";
    }

    // sync Fabric object to provided JSON
    sync(data: any = {}) {
        for (let attr in data) {
            if (attr in this) {
                this[attr] = data[attr];
            }
        }
    }
}