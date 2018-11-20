import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {Router} from '@angular/router';


@Component({
    selector: 'app-moves',
    templateUrl: './moves.component.html',
    styleUrls: ['./moves.component.css']
})
export class MovesComponent implements OnInit {
    rows: any;
    pageSize: number;
    count = 0;
    pageNumber = 0;
    sorts = [{prop: 'ts', dir: 'desc'}];
    loading = true;

    constructor(private bs: BackendService, private prefs: PreferencesService, private router: Router) {
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit() {
        this.getMovesForFabric(0, [{prop: 'ts', dir: 'desc'}]);
    }

    getMovesForFabric(pageOffset = 0, sorts = []) {
        this.loading = true;
        this.bs.getFabricsOverviewTabData(pageOffset, sorts, 'move').subscribe(
            (data) => {
                this.count = data['count'];
                this.rows = data['objects'];
                this.loading = false;
            },
            (error) => {

            });
    }

    setPage(event) {
        this.pageNumber = event.offset;
        this.getMovesForFabric(event.offset, this.sorts);
    }

    onSort(event) {
        this.sorts = event.sorts;
        this.getMovesForFabric(this.pageNumber, event.sorts);
    }

    goToDetailsPage(value) {
        let address = value.addr;
        this.prefs.endpointDetailsObject = value;
        this.router.navigate(["/ephistory", value.fabric, value.vnid, address]);

    }


}
