import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';

@Component({
    selector: 'app-per-node-history',
    templateUrl: './per-node-history.component.html',
})
export class PerNodeHistoryComponent implements OnInit {
    rows: any;
    endpoint: any;
    loading = false;
    sorts = [{prop: 'events[0].ts', dir: 'desc'}];
    pageSize: number;

    constructor(private backendService: BackendService, private prefs: PreferencesService) {
        this.endpoint = this.prefs.selectedEndpoint;
        this.pageSize = this.prefs.pageSize;
        this.rows = [];
    }

    ngOnInit() {
        if (this.endpoint.events.length === 0) {
            this.getPerNodeHistory(this.endpoint.fabric, this.endpoint.first_learn.node, this.endpoint.vnid, this.endpoint.addr);
        } else {
            this.getPerNodeHistory(this.endpoint.fabric, this.endpoint.events[0].node, this.endpoint.vnid, this.endpoint.addr);
        }
    }

    getPerNodeHistory(fabricName, node, vnid, address) {
        this.loading = true;
        this.backendService.getEndpointHistoryPerNode(fabricName, node, vnid, address).subscribe(
            (data) => {
                this.rows = [];
                for (let object of data.objects) {
                    const endpoint = object["ept.history"];
                    this.rows.push(endpoint);
                }
                this.loading = false;
            },
            (error) => {
                this.loading = false;
            }
        )
    }
}
