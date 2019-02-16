import {Component, OnInit, OnDestroy} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';
import {Fabric, FabricList} from "../../_model/fabric";
import {forkJoin, interval} from "rxjs";
import {ModalService} from '../../_service/modal.service';
import {switchMap, map} from "rxjs/operators";
import {repeatWhen, delay, takeWhile} from "rxjs/operators";

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
    fabricRunning: boolean;
    backgroundPollEnable: boolean = false;
    backgroundQlenPollEnable: boolean = false;


    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService,
                private activatedRoute: ActivatedRoute, public modalService: ModalService) {
        this.userRole = this.prefs.userRole;
        this.pageSize = this.prefs.pageSize;
        this.rows = [];
        this.fabricRunning = true;
        this.fabricFound = false;
    }

    ngOnInit() {
        this.getFabric();
        this.getManagerStatus();
    }

    ngOnDestroy(){
        this.backgroundPollEnable = false;
        this.backgroundQlenPollEnable = false;
    }

    refresh() {
        this.getManagerStatus();
        this.getFabric();
    }

    getManagerStatus(){
        this.backendService.getAppManagerStatus().subscribe(
            (data) => {
                if("manager" in data && "status" in data["manager"] && data["manager"]["status"] == "running"){
                    this.managerRunning = true;
                } else {
                    this.managerRunning = false;
                }
            }, 
            (error) => {
                this.managerRunning = false;
            }
        );
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
                            const fabricStatusObservable = this.backendService.getFabricStatus(this.fabric);
                            const macObservable = this.backendService.getActiveMacAndIps(this.fabric, 'mac');
                            const ipv4Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv4');
                            const ipv6Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv6');
                            forkJoin([fabricStatusObservable, macObservable, ipv4Observable, ipv6Observable]).subscribe(
                                ([fabricStatus, macCount, ipv4Count, ipv6Count]) => {
                                    this.fabric.uptime = fabricStatus['uptime'];
                                    this.fabric.status = fabricStatus['status'];
                                    this.fabricRunning = (this.fabric.status == 'running');
                                    this.fabric.mac = macCount['count'];
                                    this.fabric.ipv4 = ipv4Count['count'];
                                    this.fabric.ipv6 = ipv6Count['count'];
                                    this.loading = false;
                                    if(!this.backgroundPollEnable){
                                        this.backgroundPollFabric();
                                    }
                                    if(!this.backgroundQlenPollEnable){
                                        this.backgroundPollQlen();
                                    }
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

    // sliently refresh status and fabric events at regular interval
    backgroundPollFabric(){
        this.backgroundPollEnable = true;
        const fabricEventsObservable = this.backendService.getFabricByName(this.fabric.fabric);
        const fabricStatusObservable = this.backendService.getFabricStatus(this.fabric);
        forkJoin([fabricEventsObservable, fabricStatusObservable]).pipe(
            repeatWhen(delay(1000)),
            takeWhile(()=> this.backgroundPollEnable)
        ).subscribe(
            ([fabricEvents, fabricStatus]) => {
                let fabricList = new FabricList(fabricEvents);
                if (fabricList.objects.length == 1) {
                    this.rows = fabricList.objects[0].events;
                }
                this.fabric.uptime = fabricStatus['uptime'];
                this.fabric.status = fabricStatus['status'];
                this.fabricRunning = (this.fabric.status == 'running');
            },
            (error) => {
                console.log("refresh error occurred");
                console.log(error)
                this.backgroundPollEnable = false;
                return this.backgroundPollFabric();
            }
        )
    }

    // sliently refresh queue len at slower interval
    backgroundPollQlen(){
        this.backgroundQlenPollEnable = true;
        const qlenObservable = this.backendService.getAppQueueLen();
        const macObservable = this.backendService.getActiveMacAndIps(this.fabric, 'mac');
        const ipv4Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv4');
        const ipv6Observable = this.backendService.getActiveMacAndIps(this.fabric, 'ipv6');
        forkJoin([qlenObservable, macObservable, ipv4Observable, ipv6Observable]).pipe(
            repeatWhen(delay(15000)),
            takeWhile(()=> this.backgroundPollEnable)
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
                this.backgroundQlenPollEnable = false;
                return this.backgroundPollQlen();
            }
        )
    }

}
