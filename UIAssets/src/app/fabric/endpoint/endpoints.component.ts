import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';
import {Endpoint} from "../../_model/endpoint";
import {PagingService} from '../../_service/paging.service';
import {ModalService} from '../../_service/modal.service';
import {EndpointList} from 'src/app/_model/endpoint';

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
    count: number;
    pageNumber = 0;
    sorts = [];
    loading = true;
    fabricName: string;
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService,
                private activatedRoute: ActivatedRoute, public pagingService: PagingService,
                public modalService: ModalService) {
        this.rows = [];
        this.pagingService.pageSize = this.prefs.pageSize;
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
        this.rows = [];
        this.activatedRoute.parent.paramMap.subscribe(params => {
            this.pagingService.fabricName = params.get('fabric');
            if (this.fabricName != null) {
                this.backendService.getFilteredEndpoints(this.pagingService.fabricName, this.sorts, this.osFilter, this.stFilter, this.activeFilter, this.rapidFilter, 'endpoint', this.pagingService.pageOffset, this.pagingService.pageSize).subscribe(
                    (data) => {
                        let endpoint_list = new EndpointList(data);
                        this.rows = endpoint_list.objects;
                        this.pagingService.count = endpoint_list.count;
                        this.loading = false;
                    }, (error) => {
                        this.loading = false;
                        this.modalService.setModalError({
                            "body": "Failed to get endpoint data. " + error['error']['error']
                        });
                    }
                );
            }
        });
    }

    onFilterToggle() {
        this.loading = true;
        this.rows = [];
        this.pagingService.pageOffset = 0;
        this.backendService.getFilteredEndpoints(this.fabricName, this.sorts, this.osFilter, this.stFilter, 
                                                this.activeFilter, this.rapidFilter, 'endpoint', this.pagingService.pageOffset, 
                                                this.pagingService.pageSize).subscribe(
            (data) => {
                this.loading = false;
                let endpoint_list = new EndpointList(data);
                this.rows = endpoint_list.objects;
                this.pagingService.count = endpoint_list.count;
            },
            (error) => {
                this.loading = false;
                this.modalService.setModalError({
                    "body": "Failed to get endpoint data. " + error['error']['error']
                });
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
