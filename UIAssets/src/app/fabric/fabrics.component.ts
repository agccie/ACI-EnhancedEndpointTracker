import {Component} from '@angular/core';
import {BackendService} from '../_service/backend.service';
import {ActivatedRoute, Router} from '@angular/router';
import {Observable} from 'rxjs';
import {mergeMap} from 'rxjs/operators';
import {PreferencesService} from '../_service/preferences.service';
import {Fabric} from "../_model/fabric";


@Component({
    selector: 'app-fabrics',
    templateUrl: './fabrics.component.html',
    styleUrls: ['./fabrics.component.css']
})

export class FabricsComponent {
    title = 'app';
    sorts: [{ name: "fabric", dir: 'asc' }];
    rows: any;
    tabs: any;
    tabIndex = 0;
    expanded: any = {};
    events: any;
    showModal: boolean;
    modalTitle: string;
    modalBody: string;
    placeholder = "Search MAC or IP address (Ex: 00:50:56:01:11:12, 10.1.1.101, or 2001:a::65)";
    searchKey = '';
    eventObservable: Observable<any>;
    loading: boolean;
    fabric: Fabric;
    endpointExpanded: boolean;
    configurationExpanded: boolean;
    fabricName: string;

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, private activatedRoute: ActivatedRoute) {
        this.searchKey = '';
        this.events = ['event1'];
        this.endpointExpanded = true;
        this.configurationExpanded = false;
    }

    ngOnInit(): void {
        if (!this.prefs.checkedThreadStatus) {
            this.getAppStatus();
            this.prefs.checkedThreadStatus = true;
        }
        this.eventObservable = Observable.create((observer: any) => {
            observer.next(this.searchKey);
        }).pipe(
            mergeMap((token: string) => this.backendService.getSearchResults(token))
        );
        this.activatedRoute.paramMap.subscribe(params => {
            this.fabricName = params.get('fabric');
        });
    }

    getAppStatus() {
        this.backendService.getAppStatus().subscribe(
            (data) => {
                this.getAppManagerStatus();
            },
            (error) => {
                this.modalTitle = 'Error';
                this.modalBody = 'The app could not be started';
                this.showModal = true;
            }
        )
    }

    getAppManagerStatus() {
        this.backendService.getAppManagerStatus().subscribe(
            (data) => {
                if (data['manager']['status'] === 'stopped') {
                    this.modalBody = 'Thread managers not running';
                    this.modalTitle = 'Error';
                    this.showModal = true;
                }
            },
            (error) => {
                this.modalTitle = 'Error';
                this.modalBody = 'Could not reach thread manager';
                this.showModal = true;
            }
        )
    }
}
