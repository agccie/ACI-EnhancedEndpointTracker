import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';
import {ModalService} from '../../_service/modal.service';
import {EndpointList} from 'src/app/_model/endpoint';
import {CommonService} from 'src/app/_service/common.service';

@Component({
    selector: 'app-moves',
    templateUrl: './moves.component.html',
})

export class MovesComponent implements OnInit {
    rows: any;
    pageSize: number;
    count = 0;
    pageNumber = 0;
    sorts = [{prop: 'events.0.dst.ts', dir: 'desc'}];
    loading = true;
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService,
                private activatedRoute: ActivatedRoute, public modalService: ModalService,
                public commonService: CommonService) {
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit() {
        this.getMoves();
    }

    getMoves(pageOffset = this.pageNumber, sorts = this.sorts) {
        this.loading = true;
        this.activatedRoute.parent.paramMap.subscribe(params => {
            const fabricName = params.get('fabric');
            if (fabricName != null) {
                this.backendService.getFabricsOverviewTabData(fabricName, pageOffset, sorts, 'move').subscribe(
                    (data) => {
                        let endpoint_list = new EndpointList(data);
                        this.count = endpoint_list.count;
                        this.rows = endpoint_list.objects;
                        this.loading = false;
                    }, (error) => {
                        this.loading = false;
                        const msg = 'Could not fetch moves! ' + error['error']['error'];
                        this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
                    }
                );
            }
        });
    }

    setPage(event) {
        this.pageNumber = event.offset;
        this.getMoves(event.offset, this.sorts);
    }

    onSort(event) {
        this.sorts = event.sorts;
        this.getMoves(this.pageNumber, event.sorts);
    }
}
