import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import {ActivatedRoute, Router} from '@angular/router';
import {Fabric, FabricList} from "../../_model/fabric";
import {forkJoin, interval} from "rxjs";
import {ModalService} from '../../_service/modal.service';
import {switchMap, map} from "rxjs/operators";

@Component({
    selector: 'app-overview',
    templateUrl: './overview.component.html',
})

export class OverviewComponent implements OnInit {
    userRole: number = 0;
    rows: any;
    pageSize: number;
    pageNumber = 0;
    sorts = [{prop: 'timestamp', dir: 'desc'}];
    loading = true;
    restartLoading = false;
    fabric: Fabric;
    fabricFound: boolean;
    fabricName: string;
    managerRunning: boolean = true;
    fabricRunning: boolean;


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

    public pollStatus() {
        return interval(1000).pipe(switchMap(() =>
            this.backendService.getFabricStatus(this.fabric).pipe(map(
                (data) => data
            ))
        ))
    }

    // start fabric and poll status until we're at the desired status or max polls exceeded
    public startFabric() {
        let desiredStatus = "running";
        let maxRetries = 5 ; 
        this.restartLoading = true;
        this.backendService.startFabric(this.fabric).subscribe(
            (data) => {
                const poller = this.pollStatus().subscribe(
                    (data) => {
                        maxRetries--;
                        if(maxRetries<=0 || ("status" in data && data["status"]==desiredStatus)){
                            this.restartLoading = false;
                            poller.unsubscribe();
                            this.getFabric();
                        }
                    }, 
                    (error) => {
                        //some poller problem
                        poller.unsubscribe();
                    }
                )
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
        let desiredStatus = "stopped"
        let maxRetries = 5 ; 
        this.restartLoading = true;
        this.backendService.stopFabric(this.fabric).subscribe(
            (data) => {
                const poller = this.pollStatus().subscribe(
                    (data) => {
                        maxRetries--;
                        if(maxRetries<=0 || ("status" in data && data["status"]==desiredStatus)){
                            this.restartLoading = false;
                            poller.unsubscribe();
                            this.getFabric();
                        }
                    }, 
                    (error) => {
                        //some poller problem
                        poller.unsubscribe();
                    }
                )
            },
            (error) => {
                this.restartLoading = false;
                this.modalService.setModalError({
                    "body": 'Failed to stop monitor. ' + error['error']['error']
                });
            }
        );
    }


}
