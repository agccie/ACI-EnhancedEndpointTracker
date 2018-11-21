import {Component, OnInit, ViewChild, TemplateRef, ElementRef} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {Router} from '@angular/router';
import {PreferencesService} from '../../_service/preferences.service';
import {forkJoin} from "rxjs";
import { BsModalRef,BsModalService } from '../../../../node_modules/ngx-bootstrap';

@Component({
    selector: 'app-fabric-overview',
    templateUrl: './fabric-overview.component.html',
    styleUrls: ['./fabric-overview.component.css']
})

export class FabricOverviewComponent  {
    rows: any;
    sorts: any;
    showFabricModal: boolean;
    fabrics: any;
    fabricName: string;
    pageSize: number;
    loading = true;
    modalTitle='' ;
    modalBody='';
    modalIcon='' ;
    @ViewChild('myTable') table: any;
    modalRef:BsModalRef;
    @ViewChild('startStopFabricMessage') msgModalRef: TemplateRef<any> ;
    constructor(private bs: BackendService, private router: Router, private prefs: PreferencesService,private modalService: BsModalService) {
        this.sorts = {prop: 'fabric'};
        this.rows = [];
        this.showFabricModal = false;
        this.fabrics = [];
        this.fabricName = '';
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit() {
        this.getFabrics();
    }

    toggleRow(row) {
        this.table.rowDetail.toggleExpandRow(row);
    }

    getFabrics() {
        const self = this;
        this.loading = true;
        this.bs.getFabrics().subscribe(
            (data) => {
                this.fabrics = data['objects'];
                this.rows = data['objects'];
                for (let object of data['objects']) {
                    const fabric = object.fabric;
                    const fabricName = fabric.fabric;
                    const fabricStatusObservable = this.bs.getFabricStatus(fabricName);
                    const macObservable = this.bs.getActiveMacAndIps(fabricName, 'mac');
                    const ipv4Observable = this.bs.getActiveMacAndIps(fabricName, 'ipv4');
                    const ipv6Observable = this.bs.getActiveMacAndIps(fabricName, 'ipv6');
                    forkJoin([fabricStatusObservable, macObservable, ipv4Observable, ipv6Observable]).subscribe(results => {
                        fabric['status'] = results[0]['status'];
                        fabric['mac'] = results[1]['count'];
                        fabric['ipv4'] = results[2]['count'];
                        fabric['ipv6'] = results[3]['count'];
                    });
                }
                this.loading = false;
            },
            (error) => {
            }
        )
    }

    onFabricNameSubmit(fabric) {
        this.bs.createFabric(fabric).subscribe(
            (data) => {
                this.router.navigate(['/settings', this.fabricName]);
            }
        );
    }

    startStopFabric(action, fabricName) {
        let msg = '' ;
        if(action === 'start') {
            msg = 'started' ;
        }else{
            msg='stopped' ;
        }
        this.bs.startStopFabric(action, fabricName, 'testing').subscribe(
            (data) => {
                if (data['success'] === true) {
                    this.modalTitle = 'Success' ;
                    this.modalBody = 'Fabric ' + fabricName + ' ' + msg + ' successfully' ;
                    this.modalIcon = 'icon-check-square' ;
                    this.openModal(this.msgModalRef) ;
                    setTimeout(
                        ()=>{
                            this.getFabrics() ;
                        },3000
                    )
                }
            },
            (error) => {
                this.modalTitle = 'Error' ;
                this.modalBody = 'Fabric ' + fabricName + ' could not be ' + msg ;
                this.modalIcon = 'icon-error' ;
                this.openModal(this.msgModalRef) ;
            }
        )
    }

    public openModal(template: TemplateRef<any>) {
        this.modalRef = this.modalService.show(template, {
            animated: true,
            keyboard: true,
            backdrop: true,
            ignoreBackdropClick: false,
            class: 'modal-sm',
        });
    }

    public hideModal() {
        this.modalRef.hide();
    }
}
