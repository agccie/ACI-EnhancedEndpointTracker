import {Component,OnInit} from "@angular/core";
import {Router} from '@angular/router';
import {BackendService} from "../_service/backend.service";
import {PreferencesService} from "../_service/preferences.service";
import {QueueList} from "../_model/queue";
import {ModalService} from "../_service/modal.service";
import {Subject} from "rxjs";
import {debounceTime} from 'rxjs/operators';
import {FabricService} from "../_service/fabric.service";

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
    sorts = [{prop: 'total_rx_msg', dir: 'desc'}];
    searchTerm: string = "";
    searchInput: Subject<string> = new Subject();
    discoveredFabric: string = "";

    constructor(private router: Router, private backendService: BackendService, private prefs: PreferencesService, 
            public fabricService: FabricService, private modalService: ModalService) {
        this.rows = [];
        this.queues = [];
        this.pageSize = this.prefs.pageSize;
        this.pageNumber = 0;
        this.searchTerm = "";
    }

    ngOnInit(): void {
        this.getQueues()
        this.searchInput.pipe(
            debounceTime(500)
        ).subscribe(searchTextValue => {
            this.searchTerm = searchTextValue.toLowerCase();
            this.getQueues();
        });
    }

    goBack(){
        if(this.fabricService.fabric.fabric.length>0){
            this.router.navigate(['/fabric', this.fabricService.fabric.fabric, 'settings', 'connectivity']);
        } else {
            this.router.navigate(['/']);
        }
    }

    getQueues(pageOffset = this.pageNumber, sorts = this.sorts) {
        this.loading = true;
        this.backendService.getQueues(pageOffset, this.pageSize, sorts, this.searchTerm).subscribe((results: QueueList) => {
            const objects = results.objects;
            let tempRows = [];
            for (let obj of objects) {
                tempRows.push(obj['ept.queue'])
            }
            this.count = results.count;
            this.queues = tempRows;
            this.rows = tempRows;
            this.pageNumber = pageOffset;
            this.sorts = sorts;
            this.loading = false;
        }, (err) => {
            this.loading = false;
            this.modalService.setModalError({
                "body": 'Failed to load queues. ' + err['error']['error']
            });
        });
    }

    searchOnKeyUp(event){
        const searchTextValue = event.target.value.toLowerCase();
        this.searchInput.next(searchTextValue);
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
