import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {Router} from '@angular/router';
import {environment} from '../../environments/environment';
import {BackendService} from "../_service/backend.service";
import {PreferencesService} from "../_service/preferences.service";
import {forkJoin} from "rxjs";
import {Fabric} from "../_model/fabric";
import {BsModalRef, BsModalService} from "ngx-bootstrap";
import {ModalService} from '../_service/modal.service';


@Component({
    selector: 'app-welcome',
    templateUrl: './welcome.component.html',
    styleUrls: ['./welcome.component.css']
})

export class WelcomeComponent implements OnInit {
    app_mode = environment.app_mode;
    rows;
    showFabricModal: boolean;
    fabrics: Fabric[];
    fabricName: string;
    pageSize: number;
    loading = false;
    sorts = [{prop: 'fabric', dir: 'asc'}];
    fabric: Fabric;
    selectedFabric: Fabric;
    modalRef: BsModalRef;

    @ViewChild('myTable') table: any;
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, 
                private modalService: BsModalService, public localModalService: ModalService) {
        this.rows = [];
        this.showFabricModal = false;
        this.fabrics = [];
        this.fabricName = '';
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit() {
        this.getFabrics();
    }

    getFabrics(sorts = this.sorts) {
        this.loading = true;
        /** 
        this.backendService.getFabrics(sorts).subscribe(
            (data) => {
                this.fabrics = [];
                this.rows = [];
                for (let object of data.objects) {
                    const fabric = object.fabric;
                    this.fabrics.push(fabric);
                    this.rows.push(fabric);
                    const fabricStatusObservable = this.backendService.getFabricStatus(fabric);
                    const macObservable = this.backendService.getActiveMacAndIps(fabric, 'mac');
                    const ipv4Observable = this.backendService.getActiveMacAndIps(fabric, 'ipv4');
                    const ipv6Observable = this.backendService.getActiveMacAndIps(fabric, 'ipv6');
                    forkJoin([fabricStatusObservable, macObservable, ipv4Observable, ipv6Observable]).subscribe(results => {
                        fabric.status = results[0]['status'];
                        fabric.uptime = results[0]['uptime'];
                        fabric.mac = results[1]['count'];
                        fabric.ipv4 = results[2]['count'];
                        fabric.ipv6 = results[3]['count'];
                        this.loading = false;
                    }, (error) => {
                        this.loading = false;
                        const msg = 'Failed to load fabrics! ' + error['error']['error'];
                        this.localModalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
                    });
                }
                this.loading = false;
            },
            (error) => {
                this.loading = false;
            }
        )
        */
    }

    toggleFabric(fabric: Fabric) {
        if (fabric.status == 'running') {
            this.backendService.stopFabric(fabric).subscribe((data) => {
                this.getFabrics(this.sorts);
            });
        } else {
            this.backendService.startFabric(fabric).subscribe((data) => {
                this.getFabrics(this.sorts);
            });
        }
    }

    public openAddModal(template: TemplateRef<any>) {
        this.fabric = new Fabric();
        this.modalRef = this.modalService.show(template, {
            animated: true,
            keyboard: true,
            backdrop: true,
            ignoreBackdropClick: false,
            class: 'modal-lg',
        });
    }

    public openModal(template: TemplateRef<any>, fabric: Fabric) {
        this.selectedFabric = fabric;
        this.fabric = new Fabric();
        this.modalRef = this.modalService.show(template, {
            animated: true,
            keyboard: true,
            backdrop: true,
            ignoreBackdropClick: false,
            class: 'modal-lg',
        });
    }

    public hideModal() {
        this.modalRef.hide();
    }

    public onSubmit() {
        /*
        this.backendService.createFabric(this.fabric).subscribe(
            (data) => {
                this.hideModal();
                this.getFabrics();
            },
            (error) => {
                this.hideModal();
                const msg = 'Failed to create fabric! ' + error['error']['error'];
                this.localModalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        );
        */
    }

    public deleteFabric() {
        this.loading = true;
        this.backendService.deleteFabric(this.selectedFabric).subscribe((results) => {
            this.hideModal();
            this.getFabrics();
        }, (err) => {
            let msg = 'Failed to delete fabric!';
            this.hideModal();
            if (err['error'] !== undefined && err['error']['error'] !== undefined) {
                msg += ' ' + err['error']['error'];
            }
            this.loading = false;
            this.localModalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
        });
    }

    updateFilter(event) {
        const val = event.target.value.toLowerCase();
        this.rows = this.fabrics.filter(function (d) {
            return d.fabric.toLowerCase().indexOf(val) !== -1 || !val;
        });
    }
}
