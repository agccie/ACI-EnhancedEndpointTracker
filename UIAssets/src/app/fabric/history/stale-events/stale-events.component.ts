import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';

@Component({
    selector: 'app-stale-events',
    templateUrl: './stale-events.component.html',
})
export class StaleEventsComponent implements OnInit {
    rows: any;
    endpoint: any;
    nodes = [];
    loading = false;
    sorts = [{prop: 'ts', dir: 'desc'}];
    pageSize: number;

    constructor(private backendService: BackendService, private prefs: PreferencesService) {
        this.rows = [];
        this.pageSize = this.prefs.pageSize;
        this.endpoint = this.prefs.selectedEndpoint;
        this.getNodesForStaleEndpoints(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr);
    }

    ngOnInit() {
    }

    getNodesForStaleEndpoints(fabric, vnid, address) {
        this.loading = true;
        this.backendService.getNodesForOffsubnetEndpoints(fabric, vnid, address, 'stale').subscribe(
            (data) => {
                for (let i of data['objects']) {
                    this.nodes.push(i['ept.stale']['node']);
                }
                this.loading = false;
            },
            (error) => {
                this.loading = false;
            }
        );
    }
}
