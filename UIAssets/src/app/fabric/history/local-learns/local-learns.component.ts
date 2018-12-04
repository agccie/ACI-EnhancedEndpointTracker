import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import { Endpoint } from '../../../_model/endpoint';
import { ModalService } from '../../../_service/modal.service';

@Component({
    selector: 'app-local-learns',
    templateUrl: './local-learns.component.html',
})
export class LocalLearnsComponent implements OnInit {
    rows: any;
    endpoint:any;
    loading = false;
    sorts = [{prop: 'ts', dir: 'desc'}];
    pageSize: number;
    rw_bd='' ;
    rw_mac='' ;

    constructor(private bs: BackendService, private prefs: PreferencesService) {
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit() {
        this.endpoint = this.prefs.selectedEndpoint;
        this.rows = this.endpoint.events;
        this.rw_bd = Endpoint.getEventProperties('rw_bd',this.endpoint) ;
        this.rw_mac = Endpoint.getEventProperties('rw_mac',this.endpoint) ;
    }

   
}
