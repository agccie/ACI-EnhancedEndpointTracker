import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';
import {Endpoint} from "../../_model/endpoint";

@Component({
    selector: 'app-offsubnet-ept',
    templateUrl: './offsubnet-ept.component.html',
})

export class OffsubnetEptComponent implements OnInit {
    rows: any;
    pageSize: number;
    count = 0;
    pageNumber = 0;
    sorts = [{prop: 'events.0.ts', dir: 'desc'}];
    loading = true;
    endpoints: Endpoint[];

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, private activatedRoute: ActivatedRoute) {
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit() {
        this.getOffsubnetEndpoints();
    }

    getOffsubnetEndpoints(pageOffset = this.pageNumber, sorts = this.sorts) {
        this.loading = true;
        this.activatedRoute.parent.paramMap.subscribe(params => {
            const fabricName = params.get('fabric');
            if (fabricName != null) {
                this.backendService.getFabricsOverviewTabData(fabricName, pageOffset, sorts, 'offsubnet').subscribe(
                    (data) => {
                        this.endpoints = [];
                        this.rows = [];
                        for (let object of data.objects) {
                            const endpoint = object["ept.offsubnet"];
                            this.endpoints.push(endpoint);
                            this.rows.push(endpoint);
                        }
                        this.count = data['count'];
                        this.loading = false;
                    }, (error) => {
                        this.loading = false;
                    }
                );
            }
        });
    }

    setPage(event) {
        this.pageNumber = event.offset;
        this.getOffsubnetEndpoints(event.offset, this.sorts);
    }

    onSort(event) {
        this.sorts = event.sorts;
        this.getOffsubnetEndpoints(this.pageNumber, event.sorts);
    }
}
