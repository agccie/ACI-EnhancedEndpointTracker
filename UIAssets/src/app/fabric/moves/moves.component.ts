import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';

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

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, private activatedRoute: ActivatedRoute) {
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
                        this.count = data['count'];
                        this.rows = data['objects'];
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
        this.getMoves(event.offset, this.sorts);
    }

    onSort(event) {
        this.sorts = event.sorts;
        this.getMoves(this.pageNumber, event.sorts);
    }
}
