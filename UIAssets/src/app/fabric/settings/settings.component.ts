import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {environment} from '../../../environments/environment';
import {BackendService} from "../../_service/backend.service";
import {FabricService} from "../../_service/fabric.service";
import {ActivatedRoute, Router} from "@angular/router";
import {ModalService} from '../../_service/modal.service';
import {concat, forkJoin} from 'rxjs';

@Component({
    selector: 'app-settings',
    templateUrl: './settings.component.html',
})

export class SettingsComponent implements OnInit {
    app_mode = environment.app_mode;
    tabs = [];
    isLoading = false;
    @ViewChild('errorMessage') msgModal: TemplateRef<any>;
    modalIconClass = '';
    modalAlertClass = '';
    modalTitle = '';
    modalBody = '';
    modalConfirm = false;
    modalConfirmCallback = undefined;

    constructor(private backendService: BackendService, private activatedRoute: ActivatedRoute, private router: Router,
                public modalService: ModalService, public fabricService: FabricService) {
        this.tabs = [
            {name: 'Connectivity', path: 'connectivity'},
            {name: 'Notifications', path: 'notifications'},
            {name: 'Remediate', path: 'remediate'},
            {name: 'Advanced', path: 'advanced'}
        ];
        this.fabricService.fabric.init();
        this.fabricService.fabricSettings.init();
    }

    ngOnInit() {
        this.activatedRoute.parent.paramMap.subscribe(params => {
            const fabricName = params.get('fabric');
            if (fabricName != null) {
                this.isLoading = true;
                const getFabricObservable = this.backendService.getFabricByName(fabricName);
                const getFabricSettingsObservable = this.backendService.getFabricSettings(fabricName, 'default');
                forkJoin(getFabricObservable, getFabricSettingsObservable).subscribe(
                    ([fabricData, settingsData]) => {
                        this.isLoading = false;
                        if ("objects" in settingsData && settingsData.objects.length > 0 && "ept.settings" in settingsData.objects[0]) {
                            this.fabricService.fabricSettings.init();
                            this.fabricService.fabricSettings.sync(settingsData.objects[0]['ept.settings']);
                        }
                        if ("objects" in fabricData && fabricData.objects.length > 0 && "fabric" in fabricData.objects[0]) {
                            this.fabricService.fabric.init();
                            this.fabricService.fabric.sync(fabricData.objects[0]['fabric']);
                        }
                    },
                    (error) => {
                        this.isLoading = false;
                        this.setModalError();
                        this.modalTitle = 'Error';
                        this.modalBody = 'Could not fetch fabric settings. ' + error['error']['error'];
                        this.modalService.openModal(this.msgModal);
                    }
                );
            }
        });
    }

    //delete all endpoints within fabric
    deleteAllEndpoints() {
        let that = this;
        let body = 'Are you sure you want to delete all endpoint history for <strong>' + this.fabricService.fabric.fabric + '</strong>? ' +
            'This action cannot be undone.';
        this.setModalConfirm({
            "title": "Wait",
            "body": body,
            "callback": function () {
                if (that.isLoading) {
                    return;
                }
                that.isLoading = true;
                that.backendService.deleteAllEndpoints(that.fabricService.fabric.fabric).subscribe(
                    (data) => {
                        that.isLoading = false;
                    },
                    (error) => {
                        that.isLoading = false;
                        that.setModalError({
                            "body": 'Failed to update delete fabric endpoints. ' + error['error']['error']
                        });
                    }
                );
            }
        });
    }

    //delete current fabric
    deleteFabric() {
        let that = this;
        let body = 'Are you sure you want to delete fabric <strong>' + this.fabricService.fabric.fabric + '</strong>? ' +
            'This operation will delete all historical data for this fabric. This action cannot be undone.';
        this.setModalConfirm({
            "title": "Wait",
            "body": body,
            "callback": function () {
                if (that.isLoading) {
                    return;
                }
                that.isLoading = true;
                that.backendService.deleteFabric(that.fabricService.fabric).subscribe(
                    (data) => {
                        that.isLoading = false;
                        that.router.navigate(['/']);
                    },
                    (error) => {
                        that.isLoading = false;
                        that.setModalError({
                            "body": 'Failed to update delete fabric. ' + error['error']['error']
                        });
                    }
                );
            }
        })
    }

    //save current fabric settings
    saveFabric() {
        //ignore updates while loading
        if (this.isLoading) {
            return;
        }
        this.isLoading = true;
        const updateObservable = this.backendService.updateFabric(this.fabricService.fabric);
        const updateSettingsObservable = this.backendService.updateFabricSettings(this.fabricService.fabricSettings);
        forkJoin(updateObservable, updateSettingsObservable).subscribe(
            (data) => {
                this.backendService.verifyFabric(this.fabricService.fabric).subscribe(
                    (verifyData) => {
                        this.isLoading = false;
                        if ("success" in verifyData && verifyData["success"]) {
                            let that = this;
                            this.setModalConfirm({
                                "title": "Success",
                                "body": "Changes successfully applied. You must restart the fabric monitor for your changes to take effect." +
                                    " Would you like to restart now?",
                                "callback": function () {
                                    that.isLoading = true;
                                    let reason = 'monitor config change restart';
                                    const stopFabric = that.backendService.stopFabric(that.fabricService.fabric, reason);
                                    const startFabric = that.backendService.startFabric(that.fabricService.fabric, reason);
                                    concat(stopFabric, startFabric).subscribe(
                                        (restartData) => {
                                            that.isLoading = false;
                                        },
                                        (restartError) => {
                                            that.isLoading = false;
                                            that.setModalError({
                                                "body": "Failed to restart fabric. " + restartError['error']['error']
                                            });
                                        }
                                    )
                                }
                            });
                        } else {
                            let apic_label_class = "label--warning-alt";
                            let apic_label_text = "failed";
                            let apic_text = verifyData["apic_error"];
                            let ssh_label_class = "label--warning-alt";
                            let ssh_label_text = "failed";
                            let ssh_text = verifyData["ssh_error"];
                            if (apic_text.length == 0) {
                                apic_label_text = "success";
                                apic_label_class = "label--success";
                            }
                            if (ssh_text.length == 0) {
                                ssh_label_text = "success";
                                ssh_label_class = "label--success";
                            }
                            let msg = '<div class="row">' +
                                '<div class="col-md-3"><strong>APIC Credentials</strong></div>' +
                                '<div class="col-md-2"><span class="label ' + apic_label_class + '">' + apic_label_text + '</span></div>' +
                                '<div class="col-md-7">' + apic_text + '</div>' +
                                '<div class="col-md-3"><strong>SSH Credentials</strong></div>' +
                                '<div class="col-md-2"><span class="label ' + ssh_label_class + '">' + ssh_label_text + '</span></div>' +
                                '<div class="col-md-7">' + ssh_text + '</div>' +
                                '</div>';
                            this.setModalInfo({
                                "title": "Credentials verification failed",
                                "body": msg
                            })
                        }
                    },
                    (verifyError) => {
                        this.isLoading = false;
                        this.setModalError({
                            "body": 'Failed to update verify fabric settings. ' + verifyError['error']['error']
                        });
                    }
                );
            },
            (error) => {
                this.isLoading = false;
                this.setModalError({
                    "body": 'Failed to update fabric settings. ' + error['error']['error']
                });
            }
        )
    }

    openModal(content: object = {}) {
        this.modalConfirm = false;
        this.modalTitle = content["title"];
        this.modalBody = content["body"];
        this.modalService.openModal(this.msgModal);
    }

    setModalError(content: object = {}) {
        this.modalAlertClass = 'alert alert--danger';
        this.modalIconClass = 'alert__icon icon-error-outline';
        if (!("title" in content)) {
            content["title"] = "Error";
        }
        this.openModal(content);
    }

    setModalSuccess(content: object = {}) {
        this.modalAlertClass = 'alert alert--success';
        this.modalIconClass = 'alert__icon icon-check-outline';
        if (!("title" in content)) {
            content["title"] = "Success";
        }
        this.openModal(content);
    }

    setModalInfo(content: object = {}) {
        this.modalAlertClass = 'alert';
        this.modalIconClass = 'alert__icon icon-info-outline';
        if (!("title" in content)) {
            content["title"] = "Info";
        }
        this.openModal(content);
    }

    setModalConfirm(content: object = {}) {
        const self = this;
        this.modalConfirmCallback = function () {
            self.modalService.hideModal();
            if ("callback" in content) {
                content["callback"]();
            }
        };
        this.setModalInfo(content);
        this.modalConfirm = true;
    }
} 
