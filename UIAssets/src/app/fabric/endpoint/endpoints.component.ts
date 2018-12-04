import {Component, OnInit, ViewChild, TemplateRef} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';
import {Endpoint} from "../../_model/endpoint";
import {PagingService} from '../../_service/paging.service';
import { ModalService } from '../../_service/modal.service';

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
    @ViewChild('errorMsg') msgModal : TemplateRef<any> ;

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, 
        private activatedRoute: ActivatedRoute, public pagingService: PagingService, public modalService:ModalService) {
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
                        const msg = 'Could not fetch endpoints! ' + error['error']['error'] ;
                        this.modalService.setAndOpenModal('error','Error',msg,this.msgModal) ;
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
                const msg = 'Could not fetch filtered endpoints! ' + error['error']['error'] ;
                this.modalService.setAndOpenModal('error','Error',msg,this.msgModal) ;
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
