import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import {ModalService} from '../../../_service/modal.service';

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
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(private backendService: BackendService, private prefs: PreferencesService, public modalService: ModalService) {
        this.rows = [];
        this.pageSize = this.prefs.pageSize;
        this.endpoint = this.prefs.selectedEndpoint;
        this.getNodesForOffsubnetEndpoints();
    }

    ngOnInit() {
    }

    getNodesForOffsubnetEndpoints() {
        this.loading = true;
        this.backendService.getAllOffsubnetStaleEndpoints(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr, 'offsubnet').subscribe(
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
                const msg = 'Failed to load offsubnet endpoints! ' + error['error']['error'];
                this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        )
    }
}
