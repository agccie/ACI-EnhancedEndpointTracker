import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {FabricSettings} from "../../_model/fabric-settings";
import {BackendService} from "../../_service/backend.service";
import {FabricService} from "../../_service/fabric.service";
import {ActivatedRoute} from "@angular/router";
import {Fabric} from '../../_model/fabric';
import {ModalService} from '../../_service/modal.service';
import {forkJoin} from '../../../../node_modules/rxjs';

@Component({
    selector: 'app-settings',
    templateUrl: './settings.component.html',
})

export class SettingsComponent implements OnInit {
    fabric: Fabric;
    settings: FabricSettings;
    tabs = [];
    @ViewChild('errorMessage') msgModal: TemplateRef<any>;
    modalTitle = '';
    modalBody = '';
    modalIcon = '';

    constructor(private backendService: BackendService,  private activatedRoute: ActivatedRoute,
        public modalService: ModalService, public fabricService: FabricService) {
        this.tabs = [
            {name: 'Connectivity', path:'connectivity'},
            {name: 'Notifications', path:'notifications'},
            {name: 'Remediate', path:'remediate'},
            {name: 'Advanced', path:'advanced'}
        ];
        this.fabricService.fabric.init();
        this.fabricService.fabricSettings.init();
    }

    ngOnInit() {
        this.activatedRoute.parent.paramMap.subscribe(params => {
            const fabricName = params.get('fabric');
            if (fabricName != null) {
                this.getFabricSettings(fabricName, 'default');
                this.getFabricConnectivitySettings(fabricName);
            }
        });
    }

    getFabricSettings(fabricName, settings) {
        this.backendService.getFabricSettings(fabricName, settings).subscribe(
            (data) => {
                if("objects" in data && data.objects.length>0 && "ept.settings" in data.objects[0]){
                    this.fabricService.fabricSettings.init();
                    this.fabricService.fabricSettings.sync(data.objects[0]['ept.settings']);
                }
            }
        )
    }

    getFabricConnectivitySettings(fabricName: string) {
        this.backendService.getFabricByName(fabricName).subscribe(
            (data) => {
                if("objects" in data && data.objects.length>0 && "fabric" in data.objects[0]){
                    this.fabricService.fabric.init();
                    this.fabricService.fabric.sync(data.objects[0]['fabric']);
                }
            },
            (error) => {
                this.modalTitle = 'Error';
                this.modalBody = 'Could not fetch fabric settings! ' + error['error']['error'];
                this.modalIcon = 'error';
                this.modalService.openModal(this.msgModal);
            }
        )
    }

    save() {
        const updateObservable = this.backendService.updateFabric(this.fabricService.fabric);
        const updateSettingsObservable = this.backendService.updateFabricSettings(this.fabricService.fabricSettings);
        forkJoin(updateObservable, updateSettingsObservable).subscribe(
            (data) => {
                let message = '';
                if (data[0]['success'] && data[1]['success']) {
                    message += 'Successfully updated settings';
                }
                this.modalTitle = 'Success';
                this.modalBody = message;
                this.modalIcon = 'icon-check-square';
                this.modalService.openModal(this.msgModal);
            },
            (error) => {
                this.modalTitle = 'Error';
                this.modalBody = 'Failed to update fabric settings! ' + error['error']['error'];
                this.modalIcon = 'error';
                this.modalService.openModal(this.msgModal);
            }
        )
    }
} 
