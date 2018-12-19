import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {ActivatedRoute} from '@angular/router';
import {PagingService} from '../../_service/paging.service';
import {ModalService} from '../../_service/modal.service';
import {EndpointList} from 'src/app/_model/endpoint';

@Component({
    selector: 'app-cleared-ept',
    templateUrl: './cleared-ept.component.html'
})

export class ClearedEptComponent implements OnInit {
    rows: any;
    loading: any;
    sorts = [];
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(private backendService: BackendService, private activatedRoute: ActivatedRoute, public pagingService: PagingService,
                public modalService: ModalService) {
    }

    ngOnInit() {
        this.activatedRoute.parent.paramMap.subscribe(params => {
            const fabricName = params.get('fabric');
            this.pagingService.fabricName = fabricName;
            if (fabricName != null) {
                this.getClearedEndpoints();
            }
        });
    }

    getClearedEndpoints() {
        this.backendService.getFilteredEndpoints(this.pagingService.fabricName, this.sorts, false, false, false, false, 'remediate', this.pagingService.pageOffset, this.pagingService.pageSize).subscribe(
            (data) => {
                let endpoint_list = new EndpointList(data);
                this.rows = endpoint_list.objects;
                this.pagingService.count = endpoint_list.count;
                this.loading = false;
            }, (error) => {
                this.loading = false;
                const msg = 'Could not fetch cleared endpoints! ' + error['error']['error'];
                //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal, false);
            }
        );
    }

    setPage(event) {
        this.pagingService.pageOffset = event.offset;
        this.getClearedEndpoints();
    }

    onSort(event) {
        this.sorts = event.sorts;
        this.getClearedEndpoints();
    }

}


