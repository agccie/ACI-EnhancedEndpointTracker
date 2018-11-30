import {Component, OnInit} from "@angular/core";
import {BackendService} from "../_service/backend.service";
import {PreferencesService} from "../_service/preferences.service";
import {BsModalService} from "ngx-bootstrap";
import {QueueList} from "../_model/queue";

@Component({
    templateUrl: './queue.component.html',
    styleUrls: ['./queue.component.css']
})

export class QueueComponent implements OnInit {
    queues: any[];
    rows: any[];
    loading: boolean;
    pageNumber: number;
    pageSize: number;
    count: number;
    sorts = [{prop: 'dn', dir: 'asc'}];

    constructor(private backendService: BackendService, private prefs: PreferencesService, private modalService: BsModalService) {
        this.rows = [];
        this.queues = [];
        this.pageSize = this.prefs.pageSize;
        this.pageNumber = 0;
    }

    ngOnInit(): void {
        this.getQueues()
    }

    getQueues(pageOffset = this.pageNumber, sorts = this.sorts) {
        this.loading = true;
        this.backendService.getQueues(pageOffset, sorts).subscribe((results: QueueList) => {
            const objects = results.objects;
            let tempRows = [];
            for (let obj of objects) {
                tempRows.push(obj['ept.queue'])
            }
            this.count = results.count;
            this.queues = tempRows;
            this.rows = tempRows;
            this.loading = false;
        }, (err) => {
            this.loading = false;
        });
    }

    updateFilter(event) {
        const val = event.target.value.toLowerCase();
        this.rows = this.queues.filter(function (d) {
            return d.queue.toLowerCase().indexOf(val) !== -1 || !val;
        });
    }

    setPage(event) {
        this.pageNumber = event.offset;
        this.getQueues(event.offset, this.sorts);
    }

    onSort(event) {
        this.sorts = event.sorts;
        this.getQueues(this.pageNumber, event.sorts);
    }
}
