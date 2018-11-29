import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';

@Component({
    selector: 'app-local-learns',
    templateUrl: './local-learns.component.html',
})
export class LocalLearnsComponent implements OnInit {
    rows: any;
    endpoint: any;
    loading = false;
    sorts = [{prop: 'ts', dir: 'desc'}];
    pageSize: number;

    constructor(private bs: BackendService, private prefs: PreferencesService) {
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit() {
        this.endpoint = this.prefs.selectedEndpoint;
        this.rows = this.endpoint.events;
    }
}
