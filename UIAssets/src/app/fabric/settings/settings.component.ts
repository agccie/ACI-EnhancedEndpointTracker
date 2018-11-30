import {Component, OnInit, ViewChild, TemplateRef} from '@angular/core';
import {FabricSettings} from "../../_model/fabric-settings";
import {BackendService} from "../../_service/backend.service";
import {PreferencesService} from "../../_service/preferences.service";
import {ActivatedRoute, Router} from "@angular/router";
import { Fabric } from '../../_model/fabric';
import { ModalService } from '../../_service/modal.service';
import { forkJoin } from '../../../../node_modules/rxjs';

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
    @ViewChild('errorMessage') msgModal: TemplateRef<any> ;
    modalTitle = '' ;
    modalBody='' ;
    modalIcon = ''; 
    resetList:any ;
    fabricConnectivityBackup:any ;
    constructor(private backendService: BackendService, public preferencesService: PreferencesService, private activatedRoute: ActivatedRoute, 
        private router: Router, public modalService:ModalService) {
           this.resetList = {
                "connectivity":["apic_hostname","apic_cert","apic_username","apic_password","ssh_username","ssh_password"],
                "notification":["email_address",'syslog_server','syslog_port','notify_move_email','notify_move_syslog',"notify_offsubnet_email",
                "notify_offsubnet_syslog", "notify_stale_email","notify_stale_syslog","notify_rapid_syslog","notify_rapid_email","notify_clear_email","notify_clear_syslog"],
                "remediation":["auto_clear_offsubnet","auto_clear_stale"],
                "advanced":["analyze_move",'analyze_offsubnet', "analyze_stale","analyze_rapid","max_events","max_endpoint_events","max_per_node_endpoint_events",
                "refresh_rapid","rapid_threshold","rapid_holdtime","stale_no_local","stale_multiple_local","queue_init_epm_events","queue_init_events","max_per_node_endpoint_events"]   
            } ;
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
                 
                this.preferencesService.fabricSettings = data['objects'][0]['ept.settings'];
                this.settings = this.cloneObject(this.preferencesService.fabricSettings)
                
            }
        )
    }

    getFabricConnectivitySettings(fabric: string) {
        this.backendService.getFabricByName(fabric).subscribe(
            (data) => {
                this.preferencesService.fabric = data.objects[0].fabric;
                this.fabricConnectivityBackup = this.cloneObject(this.preferencesService.fabric) ;
                this.showSelectionModal = false;
            },
            (error) => {
                this.modalTitle = 'Error' ;
                this.modalBody = 'Could not fetch fabric settings! ' + error['error']['error'] ;
                this.modalIcon = 'error' ;
                this.modalService.openModal(this.msgModal) ;
            }
        )
    }

    onSubmit() {
        let connSettings = new Fabric();
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
        const fields = ['dn', 'event_count', 'controllers', 'events', 'auto_start','status','mac','ipv4','ipv6'];
        for (let field of fields) {
            if (connSettings.hasOwnProperty(field)) {
                delete connSettings[field];
            }
        }
        const updateObservable = this.backendService.updateFabric(connSettings) ;
        const updateSettingsObservable = this.backendService.updateFabricSettings(otherSettings) ;
        forkJoin(updateObservable,updateSettingsObservable).subscribe(
            (data) => {
                let message = '' ;
               if(data[0]['success'] && data[1]['success']) {
                message+='Successfully updated settings' ;
               }
               this.modalTitle = 'Success' ;
               this.modalBody = message ;
               this.modalIcon='icon-check-square' ;
               this.modalService.openModal(this.msgModal) ;
            },
            (error) => {
                this.modalTitle = 'Error' ;
                this.modalBody = 'Failed to update fabric settings! ' + error['error']['error'] ;
                this.modalIcon='error' ;
                this.modalService.openModal(this.msgModal) ;
            }
        )
    }

    public reset() {
        const params = this.activatedRoute.snapshot.children[0].url[0].path ;
        let settings = 'fabricSettings' ;
        let backup = this.settings ;
        if(params === 'connectivity') {
            settings = 'fabric'
            backup = this.fabricConnectivityBackup ;
        }
        for(let prop of this.resetList[params]) {
            this.preferencesService[settings][prop] = backup[prop] ;
        }
    }

    public cloneObject(src:Object) 
    {
        let copy = src.constructor() ;
        for(let x in src) {
            if(src.hasOwnProperty(x)) {
                copy[x] = src[x] ;
            }
        }
        return copy ;
    }
} 
