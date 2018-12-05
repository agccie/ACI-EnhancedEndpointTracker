import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import { Endpoint } from '../../../_model/endpoint';
import { ModalService } from '../../../_service/modal.service';
import { ActivatedRoute } from '../../../../../node_modules/@angular/router';

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
    rw_bd = '';
    rw_mac = '';

    constructor(private backendService: BackendService, private prefs: PreferencesService, private activatedRoute : ActivatedRoute ) {
        this.pageSize = this.prefs.pageSize;
        this.endpoint = this.prefs.selectedEndpoint ;
    }

    ngOnInit() {
            this.prefs.getEndpointParams(this,undefined,true) ;
    }


    


}
