import {Component, OnInit, OnDestroy} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';
import {Fabric, FabricList} from "../../_model/fabric";
import {forkJoin} from "rxjs";
import {ModalService} from '../../_service/modal.service';
import {repeatWhen, retryWhen, tap, delay, takeUntil} from "rxjs/operators";
import { Subject } from 'rxjs';
import {FabricService} from "../../_service/fabric.service";

@Component({
    selector: 'app-overview',
    templateUrl: './overview.component.html',
})

export class OverviewComponent implements OnInit , OnDestroy{
    userRole: number = 0;
    rows: any;
    pageSize: number;
    pageNumber = 0;
    sorts = [{prop: 'timestamp', dir: 'desc'}];
    loading = true;
    restartLoading = false;
    fabric: Fabric = new Fabric();
    fabricFound: boolean;
    fabricName: string;
    queueLen: number = -1;
    managerRunning: boolean = true;
    polling_started: boolean = false;
    private onDestroy$ = new Subject<boolean>();

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService,
                private activatedRoute: ActivatedRoute, public fabricService: FabricService, public modalService: ModalService) {
        this.userRole = this.prefs.userRole;
        this.pageSize = this.prefs.pageSize;
        this.rows = [];
        this.fabricFound = false;
    }

    ngOnInit() {
        this.getFabric();
    }

    ngOnDestroy(){
        this.onDestroy$.next(true);
        this.onDestroy$.complete();
    }

    refresh() {
        this.getFabric();
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
                            this.fabric.sync(fabric_list.objects[0]);
                            this.rows = this.fabric.events;
                            this.backgroundPollFabric();
                            this.backgroundPollQlen();
                            //flag to prevent polling loop on each refresh.
                            this.polling_started = true;
                            const macObservable = this.backendService.getActiveMacAndIps(this.fabric, 'mac');
                            const ipv4Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv4');
                            const ipv6Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv6');
                            forkJoin([macObservable, ipv4Observable, ipv6Observable]).subscribe(
                                ([macCount, ipv4Count, ipv6Count]) => {
                                    this.fabric.mac = macCount['count'];
                                    this.fabric.ipv4 = ipv4Count['count'];
                                    this.fabric.ipv6 = ipv6Count['count'];
                                    this.loading = false;
                                },
                                (error) => {
                                    this.modalService.setModalError({
                                        "body": 'Failed to get fabric status. '+error["error"]["error"]
                                    });
                                }
                            )
                        } else {
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
    
    // start fabric and poll status until we're at the desired status or max polls exceeded
    public startFabric() {
        this.restartLoading = true;
        this.backendService.startFabric(this.fabric).pipe(
            delay(1500)
        ).subscribe(
            () => {
                this.restartLoading = false;
                this.getFabric();
            },
            (error) => {
                this.restartLoading = false;
                this.modalService.setModalError({
                    "body": 'Failed to start monitor. ' + error['error']['error']
                });
            }
        );
    }

    //confirm user wants to stop fabric monitoring
    public onStopFabric() {
        let that = this;
        this.modalService.setModalConfirm({
            "callback": function(){ that.stopFabric()}, 
            "modalType": "info",
            "title": "Wait!",
            "subtitle": "Are you sure you want to stop monitoring "+this.fabricName+"?"
        });
    }

    public stopFabric() {
        this.restartLoading = true;
        this.backendService.stopFabric(this.fabric).pipe(
            delay(1500)
        ).subscribe(
            () => {
                this.restartLoading = false;
                this.getFabric();
            },
            (error) => {
                this.restartLoading = false;
                this.modalService.setModalError({
                    "body": 'Failed to stop monitor. ' + error['error']['error']
                });
            }
        )
    }

    // sliently refresh fabric events at regular interval
    backgroundPollFabric(){
        if(this.polling_started){
            return;
        }
        const fabricEventsObservable = this.backendService.getFabricByName(this.fabric.fabric);
        forkJoin([fabricEventsObservable]).pipe(
            repeatWhen(delay(2500)),
            takeUntil(this.onDestroy$),
            retryWhen( error => error.pipe(
                tap(val => {
                    console.log("refresh error occurred");
                }),
                delay(5000)
            ))
        ).subscribe(
            ([fabricEvents]) => {
                let fabricList = new FabricList(fabricEvents);
                if (fabricList.objects.length == 1) {
                    this.rows = fabricList.objects[0].events;
                }
            }
        )
    }

    // sliently refresh queue len at slower interval
    backgroundPollQlen(){
        if(this.polling_started){
            return;
        }
        const qlenObservable = this.backendService.getAppQueueLen();
        const macObservable = this.backendService.getActiveMacAndIps(this.fabric, 'mac');
        const ipv4Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv4');
        const ipv6Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv6');
        forkJoin([qlenObservable, macObservable, ipv4Observable, ipv6Observable]).pipe(
            repeatWhen(delay(15000)),
            takeUntil(this.onDestroy$),
            retryWhen( error => error.pipe(
                tap(val => {
                    console.log("refresh error occurred");
                }),
                delay(15000)
            ))
        ).subscribe(
            ([qlen, macCount, ipv4Count, ipv6Count]) => {
                this.queueLen = qlen['total_queue_len'];
                this.fabric.mac = macCount['count'];
                this.fabric.ipv4 = ipv4Count['count'];
                this.fabric.ipv6 = ipv6Count['count'];
            },
            (error) => {
                console.log("refresh qlen error occurred");
                console.log(error)
                //return this.backgroundPollQlen();
            }
        );
    }

}
