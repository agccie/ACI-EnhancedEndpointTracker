import {Component, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import {ModalService} from '../../../_service/modal.service';

@Component({
    selector: 'app-cleared',
    templateUrl: './cleared.component.html',
})

export class ClearedComponent {
    endpoint: any;
    rows: any;
    loading = true;
    pageSize = 25;
    sorts = [{prop: 'events[0].ts', dir: 'desc'}];
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(private backendService: BackendService, private prefs: PreferencesService, public modalService: ModalService) {
        this.endpoint = this.prefs.selectedEndpoint;
        this.rows = [];

    }

    getClearedEndpoints(fabricName, node, vnid, address) {
        this.loading = true;
        this.backendService.getClearedEndpoints(fabricName, node, vnid, address).subscribe(
            (data) => {
                debugger;
                this.rows = [];
                for (let object of data.objects) {
                    const endpoint = object["ept.remediate"];
                    this.rows.push(endpoint);
                }
                this.loading = false;
            },
            (error) => {
                this.loading = false;
                const msg = 'Failed to load cleared endpoints! ' + error['error']['error'];
                this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        )
    }

}
