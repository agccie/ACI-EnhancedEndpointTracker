import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';

@Component({
    selector: 'app-local-learns',
    templateUrl: './local-learns.component.html',
    styleUrls: ['./local-learns.component.css']
})
export class LocalLearnsComponent implements OnInit {

    rows: any;
    endpoint: any;
    loading = false;
    sorts = [{prop: 'ts', dir: 'desc'}];

    constructor(private bs: BackendService, private prefs: PreferencesService) {
        this.endpoint = this.prefs.selectedEndpoint;
        this.rows = this.endpoint.events;
    }

    ngOnInit() {
    }
}
