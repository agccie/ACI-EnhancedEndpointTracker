import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';
import {Endpoint} from "../../_model/endpoint";

@Component({
    selector: 'app-endpoints',
    templateUrl: './endpoints.component.html',
})
export class EndpointsComponent implements OnInit {
    rows: any[];
    osFilter = false;
    stFilter = false;
    activeFilter = false;
    rapidFilter = false;
    endpoints: Endpoint[];
    pageSize: number;
    count: number;
    pageNumber = 0;
    sorts = [];
    loading = true;
    fabricName: string;

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, private activatedRoute: ActivatedRoute) {
        this.rows = [];
        this.endpoints = [];
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit() {
        this.getEndpoints();
    }

    getEndpoints(pageOffset = this.pageNumber, sorts = this.sorts) {
        this.loading = true;
        this.activatedRoute.parent.paramMap.subscribe(params => {
            this.fabricName = params.get('fabric');
            if (this.fabricName != null) {
                this.backendService.getEndpoints(this.fabricName, pageOffset, sorts).subscribe(
                    (data) => {
                        this.endpoints = [];
                        this.rows = [];
                        for (let object of data.objects) {
                            const endpoint = object["ept.endpoint"];
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

    onFilterToggle() {
        this.loading = false;
        this.backendService.getFilteredEndpoints(this.fabricName, this.osFilter, this.stFilter).subscribe(
            (data) => {
                this.endpoints = [];
                this.rows = [];
                for (let object of data.objects) {
                    const endpoint = object["ept.endpoint"];
                    this.endpoints.push(endpoint);
                    this.rows.push(endpoint);
                }
                this.count = data['count'];
            },
            (error) => {
                this.loading = false;
            }
        )
    }

    getRowClass(endpoint) {
        if (endpoint.is_stale) {
        }
        if (endpoint.is_offsubnet) {
        }
        if (endpoint.events.length > 0 && endpoint.events[0].status === 'deleted') {
        }
    }

    setPage(event) {
        this.pageNumber = event.offset;
        this.getEndpoints(event.offset, this.sorts);
    }

    onSort(event) {
        this.sorts = event.sorts;
        this.getEndpoints(this.pageNumber, event.sorts);
    }
}
