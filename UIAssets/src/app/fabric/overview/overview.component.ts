import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
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
    endpoints$: Observable<any[]>;
    endpointInput$ = new Subject<string>();
    dropdownActive = false;
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;
    selectedEp: any;
    endpointLoading: boolean;
    fabricRunning: boolean;

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, private activatedRoute: ActivatedRoute, public modalService: ModalService) {
        this.pageSize = this.prefs.pageSize;
        this.rows = [];
        this.fabricRunning = true;
    }

    ngOnInit() {
        this.getFabric();
        this.searchEndpoint();
    }

    getFabric() {
        this.loading = true;
        this.activatedRoute.paramMap.subscribe(params => {
            const fabricName = params.get('fabric');
            if (fabricName != null) {
                this.backendService.getFabricByName(fabricName).subscribe((results: FabricList) => {
                    this.fabric = results.objects[0].fabric;
                    this.rows = this.fabric.events;
                    const fabricStatusObservable = this.backendService.getFabricStatus(this.fabric);
                    const macObservable = this.backendService.getActiveMacAndIps(this.fabric, 'mac');
                    const ipv4Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv4');
                    const ipv6Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv6');
                    forkJoin([fabricStatusObservable, macObservable, ipv4Observable, ipv6Observable]).subscribe(results => {
                        this.fabric.status = results[0]['status'];
                        this.fabric.uptime = results[0]['uptime'];
                        this.fabric.mac = results[1]['count'];
                        this.fabric.ipv4 = results[2]['count'];
                        this.fabric.ipv6 = results[3]['count'];
                        this.fabricRunning = this.fabric.status == 'running';
                    });
                    this.loading = false;
                }, (err) => {
                    this.loading = false;
                    const msg = 'Failed to load fabrics! ' + err['error']['error'];
                    this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
                });
            }
        });
    }

    onClickOfClearDatabase() {
        const msg =
            'Are you sure you want to clear all endpoints in ' + this.fabric.fabric + '?' +
            ' It may take a few moments for the updates to be seen.';
        this.modalService.setAndOpenModal('danger', 'Wait', msg, this.msgModal, true, this.clearDatabase, this);
    }

    public onStartFabric() {
        const msg =
            'Are you sure you want to start tracking endpoints on ' + this.fabric.fabric + '?' +
            ' It may take a few moments for the updates to be seen.';
        this.modalService.setAndOpenModal('danger', 'Wait', msg, this.msgModal, true, this.startFabric, this);
    }

    public onStopFabric() {
        const msg =
            'Are you sure you want to stop tracking endpoints on ' + this.fabric.fabric + '?' +
            ' It may take a few moments for the updates to be seen.';
        this.modalService.setAndOpenModal('danger', 'Wait', msg, this.msgModal, true, this.stopFabric, this);
    }

    public onEndPointChange(endpoint) {
        const addr = endpoint['ept.endpoint'].addr;
        const vnid = endpoint['ept.endpoint'].vnid;
        this.router.navigate(['/fabric', this.fabric.fabric, 'history', vnid, addr]);
    }

    private clearDatabase() {
        this.modalService.hideModal();
        this.backendService.clearDatabase(this.fabric.fabric).subscribe(
            (data) => {
                if (data['success']) {
                    const msg = 'Clear successful';
                    this.modalService.setAndOpenModal('success', 'Success', msg, this.msgModal);
                } else {
                    const msg = 'Database clearing failed';
                    this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
                }
            },
            (error) => {
                const msg = 'Database clearing failed: ' + error['error']['error'];
                this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        );
    }

    private startFabric() {
        this.modalService.hideModal();
        this.backendService.startFabric(this.fabric).subscribe(
            (data) => {
                if (data['success']) {
                    const msg = 'Start successful';
                    this.modalService.setAndOpenModal('success', 'Success', msg, this.msgModal);
                } else {
                    const msg = 'Start failed';
                    this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
                }
            },
            (error) => {
                const msg = 'Start failed: ' + error['error']['error'];
                this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        );
    }

    private stopFabric() {
        this.modalService.hideModal();
        this.backendService.stopFabric(this.fabric).subscribe(
            (data) => {
                if (data['success']) {
                    const msg = 'Stop successful';
                    this.modalService.setAndOpenModal('success', 'Success', msg, this.msgModal);
                } else {
                    const msg = 'Stop failed';
                    this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
                }
            },
            (error) => {
                const msg = 'Stop failed: ' + error['error']['error'];
                this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        );
    }

    private searchEndpoint() {
        this.endpoints$ = concat(
            of([]), // default items
            this.endpointInput$.pipe(
                debounceTime(200),
                distinctUntilChanged(),
                tap(() => this.endpointLoading = true),
                switchMap(term => this.backendService.searchEndpoint(term).pipe(
                    catchError(() => of([])), // empty list on error
                    tap(() => this.endpointLoading = false)
                ))
            )
        );
    }
}
