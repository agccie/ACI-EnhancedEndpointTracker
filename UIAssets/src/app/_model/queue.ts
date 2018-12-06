export class QueueStat {
    rx_msg: number;
    rx_msg_rate: number;
    timestamp: number;
    total_rx_msg: number;
    total_tx_msg: number;
    tx_msg: number;
    tx_msg_rate: number;

    constructor(rx_msg: number = 0, rx_msg_rate: number = 0, timestamp: number = 0, total_rx_msg: number = 0, total_tx_msg: number = 0, tx_msg: number = 0, tx_msg_rate: number = 0) {
        this.rx_msg = rx_msg;
        this.rx_msg_rate = rx_msg_rate;
        this.timestamp = timestamp;
        this.total_rx_msg = total_rx_msg;
        this.total_tx_msg = total_tx_msg;
        this.tx_msg = tx_msg;
        this.tx_msg_rate = tx_msg_rate;
    }
}

export class QueueObject {
    "ept.queue": Queue;
}

export class QueueList {
    count: number;
    objects: QueueObject[];

    public constructor() {
        this.count = 0;
        this.objects = [];
    }
}

export class Queue {
    dn: string;
    proc: string;
    queue: string;
    start_timestamp: number;
    total_rx_msg: number;
    total_tx_msg: number;
    stats_1day: QueueStat[];
    stats_1hour: QueueStat[];
    stats_1min: QueueStat[];
    stats_1week: QueueStat[];
    stats_5min: QueueStat[];


    constructor(dn: string = '', proc: string = '', queue: string = '', start_timestamp: number = 0, total_rx_msg: number = 0, total_tx_msg: number = 0, stats_1day: QueueStat[] = [], stats_1hour: QueueStat[] = [], stats_1min: QueueStat[] = [], stats_1week: QueueStat[] = [], stats_5min: QueueStat[] = []) {
        this.dn = dn;
        this.proc = proc;
        this.queue = queue;
        this.start_timestamp = start_timestamp;
        this.total_rx_msg = total_rx_msg;
        this.total_tx_msg = total_tx_msg;
        this.stats_1day = stats_1day;
        this.stats_1hour = stats_1hour;
        this.stats_1min = stats_1min;
        this.stats_1week = stats_1week;
        this.stats_5min = stats_5min;
    }
}
