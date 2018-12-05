import {Component, OnInit, ViewChild, TemplateRef} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import { ModalService } from '../../../_service/modal.service';

@Component({
    selector: 'app-move-events',
    templateUrl: './move-events.component.html',
})
export class MoveEventsComponent implements OnInit {
    rows: any;
    endpoint: any;
    loading = false;
    sorts = [{prop: 'ts', dir: 'desc'}];
    pageSize: number;
    @ViewChild('errorMsg') msgModal : TemplateRef<any>;
    constructor(private backendService: BackendService, private prefs: PreferencesService, public modalService:ModalService) {
        this.endpoint = this.prefs.selectedEndpoint;
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit() {
        this.getMoveEventsForEndpoint(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr);
    }

    getMoveEventsForEndpoint(fabric, vnid, address) {
        this.loading = true;
        this.backendService.getMoveEventsForEndpoint(fabric, vnid, address).subscribe(
            (data) => {
                this.rows = data['objects'][0]['ept.move']['events'];
                this.loading = false;
            },
            (error) => {
                this.loading = false;
                const msg = 'Failed to load endpoint move events! ' + error['error']['error'] ;
                this.modalService.setAndOpenModal('error','Error',msg,this.msgModal) ;
            }
        )
    }
}
