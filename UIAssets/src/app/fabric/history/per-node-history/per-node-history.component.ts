import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import {forkJoin} from 'rxjs';
import {ModalService} from '../../../_service/modal.service';
import {ActivatedRoute} from '@angular/router';

@Component({
    selector: 'app-per-node-history',
    templateUrl: './per-node-history.component.html',
})
export class PerNodeHistoryComponent implements OnInit {
    rows: any;
    endpoint: any;
    loading = false;
    sorts = [{prop: 'events[0].ts', dir: 'desc'}];
    pageSize: number;
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(private backendService: BackendService, private prefs: PreferencesService, public modalService: ModalService, private activatedRoute: ActivatedRoute) {
        this.endpoint = this.prefs.selectedEndpoint;
        this.pageSize = this.prefs.pageSize;
        this.rows = [];
    }

    ngOnInit() {
        if (!this.endpoint) {
            this.prefs.getEndpointParams(this, () => {
                this.getNodesForEndpoint();
            });
        } else {
            this.getNodesForEndpoint();
        }
    }

    getNodesForEndpoint() {
        let cumulativeEvents = [];
        let obsList = [];
        this.backendService.getNodesForOffsubnetEndpoints(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr, 'history').subscribe(
            (data) => {
                for (let items of data['objects']) {
                    let node = (items['ept.history']['node']);
                    obsList.push(this.backendService.getPerNodeHistory(this.endpoint.fabric, node, this.endpoint.vnid, this.endpoint.addr));
                }
                forkJoin(obsList).subscribe(
                    (data) => {
                        for (let item of data) {
                            for (let event of item['objects'][0]['ept.history']['events']) {
                                event.node = item['objects'][0]['ept.history']['node'];
                            }
                            cumulativeEvents = cumulativeEvents.concat(item['objects'][0]['ept.history']['events']);
                        }
                        this.rows = cumulativeEvents;
                    },
                    (error) => {
                        const msg = 'Could not fetch nodes for endpoint! ' + error['error']['error'];
                        this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal, false);
                    }
                )
            },
            (error) => {
                const msg = 'Could not fetch nodes for endpoint! ' + error['error']['error'];
                this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal, false);
            }
        );
    }
}
