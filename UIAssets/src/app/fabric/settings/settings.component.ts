import {Component, OnInit} from '@angular/core';
import {FabricSettings} from "../../_model/fabric-settings";
import {BackendService} from "../../_service/backend.service";
import {PreferencesService} from "../../_service/preferences.service";
import {ActivatedRoute, Router} from "@angular/router";

@Component({
    selector: 'app-settings',
    templateUrl: './settings.component.html',
})

export class SettingsComponent implements OnInit {
    settings: FabricSettings;
    tabs = [];
    showSelectionModal = false;
    fabrics = [];
    fabric: any;

    constructor(private backendService: BackendService, public preferencesService: PreferencesService, private activatedRoute: ActivatedRoute, private router: Router) {

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

    getFabricSettings(fabric, settings) {
        this.backendService.getFabricSettings(fabric, settings).subscribe(
            (data) => {
                this.settings = data['objects'][0]['ept.settings'];
                this.preferencesService.fabricSettings = this.settings;
            }
        )
    }

    getFabricConnectivitySettings(fabric: string) {
        this.backendService.getFabricByName(fabric).subscribe(
            (data) => {
                this.preferencesService.fabric = data.objects[0].fabric;
                this.showSelectionModal = false;
            },
            (error) => {
            }
        )
    }

    onSubmit() {
        let connSettings = {};
        let otherSettings = new FabricSettings();
        for (let prop in this.preferencesService.fabric) {
            if (this.preferencesService.fabric[prop] !== undefined && (this.preferencesService.fabric[prop] !== '' || this.preferencesService.fabric[prop] !== 0)) {
                connSettings[prop] = this.preferencesService.fabric[prop];
            }
        }
        for (let prop in this.preferencesService.fabricSettings) {
            if (this.preferencesService.fabricSettings[prop] !== undefined && (this.preferencesService.fabricSettings[prop] !== '' || this.preferencesService.fabricSettings[prop] !== 0)) {
                otherSettings[prop] = this.preferencesService.fabricSettings[prop];
            }
        }
        if (otherSettings.hasOwnProperty('dn')) {
            delete otherSettings['dn'];
        }
        const fields = ['dn', 'event_count', 'controllers', 'events', 'auto_start'];
        for (let field of fields) {
            if (connSettings.hasOwnProperty(field)) {
                delete connSettings[field];
            }
        }
        this.backendService.updateFabric(this.preferencesService.fabric).subscribe(
            (data) => {
            },
            (error) => {

            }
        );
        this.backendService.updateFabricSettings(this.preferencesService.fabricSettings).subscribe(
            (data) => {

            },
            (error) => {

            }
        )
    }

    isSubmitDisabled() {
        let fabricFormValid = true;
        let fabricSettingsFormValid = true;
        for (let prop in this.preferencesService.fabric) {
            if (this.preferencesService.fabric[prop] === undefined || this.preferencesService.fabric[prop] === '') {
                fabricFormValid = false;
                break;
            }
        }
        for (let prop in this.preferencesService.fabricSettings) {
            if (this.preferencesService.fabricSettings[prop] === undefined || this.preferencesService.fabricSettings[prop] === '') {
                fabricSettingsFormValid = false;
                break;
            }
        }
        return (fabricFormValid && fabricSettingsFormValid);
    }
}
