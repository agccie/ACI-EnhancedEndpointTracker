import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';
import {Endpoint} from "../../_model/endpoint";
import {PagingService} from '../../_service/paging.service';

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

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, private activatedRoute: ActivatedRoute, public pagingService: PagingService) {
        this.rows = [];
        this.endpoints = [];
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit() {
        this.activatedRoute.parent.paramMap.subscribe(params => {
            this.fabricName = params.get('fabric');
            if (this.fabricName != null) {
                this.getEndpoints();
            }
        });
    }

    getEndpoints() {
        this.loading = true;
        this.activatedRoute.parent.paramMap.subscribe(params => {
            this.pagingService.fabricName = params.get('fabric');
            if (this.fabricName != null) {
                this.backendService.getFilteredEndpoints(this.pagingService.fabricName, this.sorts, this.osFilter, this.stFilter, this.activeFilter, this.rapidFilter, 'endpoint', this.pagingService.pageOffset, this.pagingService.pageSize).subscribe(
                    (data) => {
                        this.endpoints = [];
                        this.rows = [];
                        for (let object of data.objects) {
                            const endpoint = object["ept.endpoint"];
                            this.endpoints.push(endpoint);
                            this.rows.push(endpoint);
                        }
                        this.pagingService.count = data['count'];
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
        this.backendService.getFilteredEndpoints(this.fabricName, this.sorts, this.osFilter, this.stFilter, this.activeFilter, this.rapidFilter, 'endpoint', this.pagingService.pageOffset, this.pagingService.pageSize).subscribe(
            (data) => {
                this.endpoints = [];
                this.rows = [];
                for (let object of data.objects) {
                    const endpoint = object["ept.endpoint"];
                    this.endpoints.push(endpoint);
                    this.rows.push(endpoint);
                }
                this.pagingService.count = data['count'];
            },
            (error) => {
                this.loading = false;
            }
        )
    }

    setPage(event) {
        this.pagingService.pageOffset = event.offset;
        this.getEndpoints();
    }

    onSort(event) {
        this.sorts = event.sorts;
        this.getEndpoints();
    }
}
