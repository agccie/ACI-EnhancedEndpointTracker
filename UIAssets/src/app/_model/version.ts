export class Version {
    author: string;
    branch: string;
    commit: string;
    date: string;
    timestamp: Date;
    version: string;

    constructor(author: string = '', branch: string = '', commit: string = '', date: string = '',
                timestamp: Date = new Date(), version: string = '') {
        this.author = author;
        this.branch = branch;
        this.commit = commit;
        this.date = date;
        this.timestamp = timestamp;
        this.version = version;
    }
}