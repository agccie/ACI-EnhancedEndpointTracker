import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';

@Component({
    selector: 'app-per-node-history',
    templateUrl: './per-node-history.component.html',
    styleUrls: ['./per-node-history.component.css']
})
export class PerNodeHistoryComponent implements OnInit {
    rows: any;
    endpoint: any;
    loading = false;

    constructor(private bs: BackendService, private prefs: PreferencesService) {
        this.endpoint = this.prefs.selectedEndpoint;
        this.rows = [];
        if (this.endpoint.events.length === 0) {
            this.getPerNodeHistory(this.endpoint.fabric, this.endpoint.first_learn.node, this.endpoint.vnid, this.endpoint.addr);
        } else {
            this.getPerNodeHistory(this.endpoint.fabric, this.endpoint.events[0].node, this.endpoint.vnid, this.endpoint.addr);
        }

    }

    ngOnInit() {
    }

    getPerNodeHistory(fabric, node, vnid, address) {
        this.bs.getPerNodeHistory(fabric, node, vnid, address).subscribe(
            (data) => {
                this.rows = data['objects'];
            },
            (error) => {
                console.log(error);
            }
        )
    }


}
