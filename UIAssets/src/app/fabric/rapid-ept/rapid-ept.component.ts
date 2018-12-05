import {Component, OnInit, ViewChild, TemplateRef} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {ActivatedRoute} from '@angular/router';
import {PagingService} from '../../_service/paging.service';
import { ModalService } from '../../_service/modal.service';

@Component({
    selector: 'app-rapid-ept',
    templateUrl: './rapid-ept.component.html',
})

export class RapidEptComponent implements OnInit {
    rows: any;
    loading: any;
    sorts = [];
    @ViewChild('errorMsg') msgModal : TemplateRef<any> ;
    constructor(private backendService: BackendService, private activatedRoute: ActivatedRoute, public pagingService: PagingService,public modalService:ModalService) {

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
        this.backendService.getFilteredEndpoints(this.pagingService.fabricName, this.sorts, false, false, false, false, 'rapid', this.pagingService.pageOffset, this.pagingService.pageSize).subscribe(
            (data) => {
                this.pagingService.count = data['count'];
                this.rows = data['objects'];
                this.loading = false;
            }, (error) => {
                this.loading = false;
                const msg = 'Failed to load rapid endpoints! ' + error['error']['error'] ;
                this.modalService.setAndOpenModal('error','Error',msg,this.msgModal) ;

            }
        );
    }

    setPage(event) {
        this.pagingService.pageOffset = event.offset;
        this.getRapidEndpoints();
    }

    onSort(event) {
        this.sorts = event.sorts;
        this.getRapidEndpoints();
    }
}
