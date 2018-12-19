import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';
import {Fabric, FabricList} from "../../_model/fabric";
import {concat, forkJoin, Observable, of, Subject} from "rxjs";
import {ModalService} from '../../_service/modal.service';
import {catchError, debounceTime, distinctUntilChanged, switchMap, tap} from "rxjs/operators";

@Component({
    selector: 'app-overview',
    templateUrl: './overview.component.html',
})

export class OverviewComponent implements OnInit {
    rows: any;
    pageSize: number;
    pageNumber = 0;
    sorts = [{prop: 'timestamp', dir: 'desc'}];
    loading = true;
    fabric: Fabric;
    fabricFound: boolean;
    fabricName: string;
    dropdownActive = false;
    selectedEp: any;
    fabricRunning: boolean;
    // search bar variables
    endpoints$: Observable<any[]>;
    endpointInput$ = new Subject<string>();
    endpointLoading: boolean = false;
    endpointList = [];
    endpointMatchCount: number = 0;

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService,
                private activatedRoute: ActivatedRoute, public modalService: ModalService) {
        this.pageSize = this.prefs.pageSize;
        this.rows = [];
        this.fabricRunning = true;
        this.fabricFound = false;
    }

    ngOnInit() {
        this.getFabric();
        this.searchEndpoint();
    }

    getFabric() {
        this.loading = true;
        this.activatedRoute.paramMap.subscribe(params => {
            this.fabricName = params.get('fabric');
            if (this.fabricName != null) {
                this.backendService.getFabricByName(this.fabricName).subscribe(
                    (data) => {
                        let fabric_list = new FabricList(data);
                        if (fabric_list.objects.length > 0) {
                            this.fabricFound = true;
                            this.fabric = fabric_list.objects[0];
                            this.rows = this.fabric.events;
                            const fabricStatusObservable = this.backendService.getFabricStatus(this.fabric);
                            const macObservable = this.backendService.getActiveMacAndIps(this.fabric, 'mac');
                            const ipv4Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv4');
                            const ipv6Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv6');
                            forkJoin([fabricStatusObservable, macObservable, ipv4Observable, ipv6Observable]).subscribe(
                                (results) => {
                                    this.loading = false;
                                    this.fabric.status = results[0]['status'];
                                    this.fabric.uptime = results[0]['uptime'];
                                    this.fabric.mac = results[1]['count'];
                                    this.fabric.ipv4 = results[2]['count'];
                                    this.fabric.ipv6 = results[3]['count'];
                                    this.fabricRunning = (this.fabric.status == 'running');
                                },
                                (error) => {
                                    this.loading = false;
                                    this.modalService.setModalError({
                                        "body": 'Failed to load fabric state. ' + error['error']['error']
                                    });
                                }
                            );
                        } else {
                            this.loading = false;
                            this.modalService.setModalError({
                                "body": 'Failed to load fabric, invalid results returned.'
                            });
                        }
                    }, (error) => {
                        this.loading = false;
                        this.modalService.setModalError({
                            "body": 'Failed to load fabric. ' + error['error']['error']
                        });
                    }
                );
            }
        });
    }

    public startFabric() {
        this.backendService.startFabric(this.fabric).subscribe(
            (data) => {
                // TODO stop loading
            },
            (error) => {
                this.modalService.setModalError({
                    "body": 'Failed to start monitor. ' + error['error']['error']
                });
            }
        );
    }

    public stopFabric() {
        this.backendService.stopFabric(this.fabric).subscribe(
            (data) => {
                // TODO stop loading
            },
            (error) => {
                this.modalService.setModalError({
                    "body": 'Failed to stop monitor. ' + error['error']['error']
                });
            }
        );
    }

    public onEndPointChange(endpoint) {
        if('ept.endpoint' in endpoint){
            const addr = endpoint['ept.endpoint'].addr;
            const vnid = endpoint['ept.endpoint'].vnid;
            const fabric = endpoint['ept.endpoint'].fabric;
            this.router.navigate(['/fabric', fabric, 'history', vnid, addr]);
        }
    }

    private searchEndpoint() {
        this.endpoints$ = concat(
            of([]), // default items
            this.endpointInput$.pipe(
                debounceTime(200),
                distinctUntilChanged(),
                tap(() => {
                    this.endpointLoading = true;
                    this.endpointMatchCount = 0;
                    this.endpointList = [];
                }),
                switchMap(term => this.backendService.searchEndpoint(term, this.fabricName).pipe(
                    catchError(() => of([])), // empty list on error
                    tap(() => {
                        this.endpointLoading = false;
                    })
                ))
            )
        );
        this.endpoints$.subscribe(
            (data) => {
                if("objects" in data && "count" in data){
                    this.endpointList = data["objects"];
                    // add dummy shim entry at index 0 
                    this.endpointList.unshift("");
                    this.endpointMatchCount = data["count"];
                }
            }
        );
    }
}
