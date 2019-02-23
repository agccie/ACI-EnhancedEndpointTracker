import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {ActivatedRoute} from '@angular/router';
import {PagingService} from '../../_service/paging.service';
import {ModalService} from '../../_service/modal.service';
import {EndpointList} from 'src/app/_model/endpoint';

@Component({
    selector: 'app-rapid-ept',
    templateUrl: './rapid-ept.component.html',
})

export class RapidEptComponent implements OnInit {
    rows: any;
    loading: boolean = false;
    pageSize: number;
    pageNumber: number = 0;
    count: number = 0;
    sorts = [];
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(private backendService: BackendService, private activatedRoute: ActivatedRoute,public pagingService: PagingService,
                public modalService: ModalService) {
        this.pageSize = this.pagingService.pageSize;
    }

    ngOnInit() {
        this.activatedRoute.parent.paramMap.subscribe(params => {
            const fabricName = params.get('fabric');
            this.pagingService.fabricName = fabricName;
            if (fabricName != null) {
                this.getRapidEndpoints();
            }
        });
    }

    getRapidEndpoints() {
        this.loading = true;
        this.backendService.getFilteredEndpoints(this.pagingService.fabricName, this.sorts, false, false, false, false, 'rapid', this.pageNumber, this.pageSize).subscribe(
            (data) => {
                let endpoint_list = new EndpointList(data);
                this.count = endpoint_list.count;
                this.rows = endpoint_list.objects;
                this.loading = false;
            }, (error) => {
                this.loading = false;
                this.modalService.setModalError({
                    "body": "Failed to get endpoint data. " + error['error']['error']
                });
            }
        );
    }

    setPage(event) {
        this.pageNumber = event.offset;
        this.getRapidEndpoints();
    }

    onSort(event) {
        this.sorts = event.sorts;
        this.getRapidEndpoints();
    }
}
