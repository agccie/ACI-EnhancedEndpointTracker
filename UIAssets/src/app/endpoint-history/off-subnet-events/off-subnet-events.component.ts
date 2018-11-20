import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';

@Component({
    selector: 'app-off-subnet-events',
    templateUrl: './off-subnet-events.component.html',
    styleUrls: ['./off-subnet-events.component.css']
})
export class OffSubnetEventsComponent implements OnInit {
    rows: any;
    nodes = [];
    endpoint: any;
    loading = false;
    sorts = [{prop: 'ts', dir: 'desc'}];

    constructor(private bs: BackendService, private prefs: PreferencesService) {
        this.rows = [];
        this.endpoint = this.prefs.selectedEndpoint;
        this.getNodesForOffsubnetEndpoints(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr);
    }

    ngOnInit() {
    }

    getNodesForOffsubnetEndpoints(fabric, vnid, address) {
        this.bs.getNodesForOffsubnetEndpoints(fabric, vnid, address, 'offsubnet').subscribe(
            (data) => {
                for (let i of data['objects']) {
                    this.nodes.push(i['ept.offsubnet']['node']);
                }
            },
            (error) => {
            }
        )
    }
}
