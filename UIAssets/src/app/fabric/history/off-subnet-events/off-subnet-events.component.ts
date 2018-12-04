import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';

@Component({
    selector: 'app-off-subnet-events',
    templateUrl: './off-subnet-events.component.html',
})
export class OffSubnetEventsComponent implements OnInit {
    rows: any;
    nodes = [];
    endpoint: any;
    loading = false;
    sorts = [{prop: 'ts', dir: 'desc'}];
    pageSize: number;

    constructor(private backendService: BackendService, private prefs: PreferencesService) {
        this.rows = [];
        this.pageSize = this.prefs.pageSize;
        this.endpoint = this.prefs.selectedEndpoint;
        this.getNodesForOffsubnetEndpoints(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr);
    }

    ngOnInit() {
    }

    getNodesForOffsubnetEndpoints(fabricName, vnid, address) {
        this.loading = true;
        this.backendService.getAllOffsubnetEndpoints().subscribe(
            (data) => {
                this.rows = [];
                for (let object of data.objects) {
                    const endpoint = object["ept.offsubnet"];
                    for (let event of endpoint.events) {
                        event.node = endpoint['node'];
                        this.rows.push(event);
                    }

                }
                this.loading = false;
            },
            (error) => {
                this.loading = false;
            }
        )
    }
}
