import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';
import {Endpoint} from "../../_model/endpoint";
import {ModalService} from '../../_service/modal.service';

@Component({
    selector: 'app-stale-ept',
    templateUrl: './stale-ept.component.html',
})
export class StaleEptComponent implements OnInit {
    rows: any;
    pageSize: number;
    count = 0;
    pageNumber = 0;
    loading = true;
    sorts = [{prop: 'events.0.ts', dir: 'desc'}];
    endpoints: Endpoint[];
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService,
                private activatedRoute: ActivatedRoute, public modalService: ModalService) {
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit() {
        this.getStaleEndpoints();
    }

    getStaleEndpoints(pageOffset = this.pageNumber, sorts = this.sorts) {
        this.loading = true;
        this.activatedRoute.parent.paramMap.subscribe(params => {
            const fabricName = params.get('fabric');
            if (fabricName != null) {
                this.backendService.getFabricsOverviewTabData(fabricName, pageOffset, sorts, 'stale').subscribe(
                    (data) => {
                        this.endpoints = [];
                        this.rows = [];
                        for (let object of data.objects) {
                            const endpoint = object["ept.stale"];
                            this.endpoints.push(endpoint);
                            this.rows.push(endpoint);
                        }
                        this.count = data['count'];
                        this.loading = false;
                    }, (error) => {
                        this.loading = false;
                        const msg = 'Failed to load stale endpoints! ' + error['error']['error'];
                        this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
                    }
                );
            }
        });
    }

    setPage(event) {
        this.pageNumber = event.offset;
        this.getStaleEndpoints(event.offset, this.sorts);
    }

    onSort(event) {
        this.sorts = event.sorts;
        this.getStaleEndpoints(this.pageNumber, event.sorts);
    }
}
