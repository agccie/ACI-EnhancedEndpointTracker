import {Component, OnInit, TemplateRef, ViewChild} from "@angular/core";
import {BackendService} from "../_service/backend.service";
import {PreferencesService} from "../_service/preferences.service";
import {QueueList} from "../_model/queue";
import {ModalService} from "../_service/modal.service";

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
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(private backendService: BackendService, private prefs: PreferencesService, private modalService: ModalService) {
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
            this.modalService.setModalError({
                "body": 'Failed to load queues. ' + err['error']['error']
            });
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
