import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {Router} from '@angular/router';
import {environment} from '../../environments/environment';
import {BackendService} from "../_service/backend.service";
import {PreferencesService} from "../_service/preferences.service";
import {Fabric, FabricList} from "../_model/fabric";
import {ModalService} from '../_service/modal.service';


@Component({
    selector: 'app-welcome',
    templateUrl: './welcome.component.html',
    styleUrls: ['./welcome.component.css']
})

export class WelcomeComponent implements OnInit {
    app_mode = environment.app_mode;
    rows = [];
    showFabricModal: boolean;
    fabrics: Fabric[];
    fabricName: string;
    loadingCount = 0;
    sorts = [{prop: 'fabric', dir: 'asc'}];
    @ViewChild('addFabric') addFabricModal: TemplateRef<any>;

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService,
                public modalService: ModalService) {
        this.rows = [];
        this.fabrics = [];
        this.fabricName = '';
    }

    ngOnInit() {
        this.getFabrics();
    }

    getFabricStatus(fabric:Fabric){
        this.loadingCount++;
        this.backendService.getFabricStatus(fabric).subscribe(
            (data) => {
                this.loadingCount--;
                if("status" in data){
                    fabric.status = data["status"]
                }
                if("uptime" in data){
                    fabric.uptime = data["uptime"]
                }
            },
            (error) => {
                this.loadingCount--;
                this.modalService.setModalError({
                    "body": 'Failed to load fabric status for '+fabric.fabric+'. '+ error['error']['error']
                });
            }
        )
    }

    getFabricCount(fabric:Fabric, count_type:string){
        this.loadingCount++;
        this.backendService.getActiveMacAndIps(fabric, count_type).subscribe(
            (data) => {
                this.loadingCount--;
                if("count" in data){
                    fabric[count_type] = data["count"];
                }
            },
            (error) => {
                this.loadingCount--;
                this.modalService.setModalError({
                    "body": 'Failed to load fabric active count for '+fabric.fabric+'. '+ error['error']['error']
                });
            }
        )
    }

    getFabrics(sorts = this.sorts) {
        this.loadingCount = 1;
        this.backendService.getFabrics(sorts).subscribe(
            (data) => {
                let fabric_list = new FabricList(data);
                this.fabrics = [];
                this.rows = [];
                this.loadingCount--;
                for (const fabric of fabric_list.objects) {
                    this.fabrics.push(fabric);
                    this.rows.push(fabric);
                    this.getFabricStatus(fabric);
                    this.getFabricCount(fabric, "mac");
                    this.getFabricCount(fabric, "ipv4");
                    this.getFabricCount(fabric, "ipv6");
                }
            },
            (error) => {
                this.loadingCount = 0;
                this.modalService.setModalError({
                    "body": 'Failed to load fabrics. ' + error['error']['error']
                });
            }
        )
    }

    public updateFilter(event) {
        const val = event.target.value.toLowerCase();
        this.rows = this.fabrics.filter(function (d) {
            return d.fabric.toLowerCase().indexOf(val) !== -1 || !val;
        });
    }

    public showAddFabric(){
        this.modalService.openModal(this.addFabricModal)
    }

    public submitFabric(){
        this.modalService.hideModal();
        this.loadingCount++;
        this.backendService.createFabric(new Fabric({"fabric":this.fabricName})).subscribe(
            (data) => {
                this.loadingCount--;
                this.router.navigate(['/fabric', this.fabricName, 'settings', 'connectivity']);
            },
            (error) => {
                this.loadingCount--;
                this.modalService.setModalError({
                    "body": 'Failed to create fabric. ' + error['error']['error']
                })
            }
        );
    }
}
