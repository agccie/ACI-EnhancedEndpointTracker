import {Component, OnInit, ViewChild, TemplateRef} from '@angular/core';
import {PreferencesService} from '../../_service/preferences.service';
import {BackendService} from '../../_service/backend.service';
import {ActivatedRoute, Router} from '@angular/router';
import {forkJoin} from '../../../../node_modules/rxjs' ;
import { ModalService } from '../../_service/modal.service';
import { Fabric } from '../../_model/fabric';

@Component({
    selector: 'app-endpoint-history',
    templateUrl: './endpoint-history.component.html',
})

export class EndpointHistoryComponent implements OnInit {
    tabs: any;
    endpoint: any;
    endpointStatus = '';
    fabricDetails = '';
    staleoffsubnetDetails = '';
    vpcDetails = '' ;
    modalTitle = '';
    modalBody = '';
    modalIcon = 'error';
    fabricName: string;
    vnid: string;
    address: string;
    rw_mac = '' ;
    rw_bd = '' ;
    clearEndpointOptions: any;
    clearNodes = [];
    loading = true;
    dropdownActive: false;
    decisionBox = false ;
    callback:any ;
    @ViewChild('errorMsg') msgModal : TemplateRef<any> ;
    @ViewChild('clearMsg') clearModal : TemplateRef<any> ;
    offsubnetList = [] ;
    staleList = [] ;
    addNodes = (term) => {
        return {label: term, value: term};
    };

    constructor(private prefs: PreferencesService, private backendService: BackendService, private activatedRoute: ActivatedRoute, 
        private router: Router, public modalService:ModalService) {
        this.clearEndpointOptions = [
            {label: 'Select all', value: 0},
            {label: 'Offsubnet endpoints', value: 1},
            {label: 'Stale Endpoints', value: 2}
        ];
        this.tabs = [
            {name: ' Local Learns', icon: 'icon-computer', path: 'locallearns'},
            {name: ' Per Node History', icon: 'icon-clock', path: 'pernodehistory'},
            {name: ' Move Events', path: 'moveevents', icon: 'icon-panel-shift-right'},
            {name: ' Off-Subnet Events', path: 'offsubnetevents', icon: 'icon-jump-out'},
            {name: ' Stale Events', path: 'staleevents', icon: 'icon-warning'},
            {name: ' Rapid', path:'rapid', icon:'icon-too-fast'},
            {name: ' Cleared', path:'cleared', icon:'icon-delete'}
        ];

    }

    ngOnInit() {
        this.loading = true;
        this.activatedRoute.parent.paramMap.subscribe(params => {
            this.fabricName = params.get('fabric');
            if(this.fabricName != undefined) {
                this.activatedRoute.paramMap.subscribe(params => {
                    this.vnid = params.get('vnid');
                    this.address = params.get('address');
                    this.getEndpoint(this.fabricName, this.vnid, this.address);
                    this.loading = false;
                }, error => {
                    this.loading = false;
                });
            }

        }, error => {
            this.loading = false;
        });
    }

    getEventProperties(property) {
        if (this.endpoint.events.length > 0) {
            return this.endpoint.events[0][property];
        } else if (this.endpoint.hasOwnProperty('first_learn')) {
            return this.endpoint.first_learn[property];
        } else {
            return '';
        }
    }

    setupStatusAndInfoStrings() {
        const status = this.getEventProperties('status');
        const node = this.getEventProperties('node');
        const intf = this.getEventProperties('intf_name');
        const encap = this.getEventProperties('encap');
        const epgname = this.getEventProperties('epg_name');
        const vrfbd = this.getEventProperties('vnid_name');
        const mac = this.getEventProperties('rw_mac') ;
        const mac_bd = this.getEventProperties('rw_bd') ;
        if(mac != '' && mac_bd !='') {
            this.rw_mac = mac ;
            this.rw_bd = mac_bd ;
        }
        this.staleoffsubnetDetails = '';
        if (this.endpoint.is_offsubnet) {
            this.staleoffsubnetDetails += 'Currently offsubnet on node ' + node + '\n';
            const currentlyOffsubnet = this.backendService.offsubnetStaleEndpointHistory(this.fabricName,this.vnid,this.address,'is_offsubnet','endpoint') ;
            const offsubnetHistory = this.backendService.offsubnetStaleEndpointHistory(this.fabricName,this.vnid,this.address,'is_offsubnet','history') ;
            forkJoin(currentlyOffsubnet,offsubnetHistory).subscribe(
                (data) => {
                    const is_offsubnet = data[0]['objects'][0]['ept.endpoint']['is_offsubnet'] ;
                    this.endpoint.is_offsubnet = is_offsubnet ;
                    if(is_offsubnet) {
                        for(let item of data[1]['objects']) {
                            this.offsubnetList.push(item['ept.history'].node) ;
                        }
                    }
                },
                (error) => {
                    const msg = 'Could not check if the endpoint has offsubnet nodes! ' + error['error']['error'] ;
                    this.modalService.setAndOpenModal('error','Error',msg,this.msgModal,false) ;
                }
            )
        }
        if (this.endpoint.is_stale) {
            this.staleoffsubnetDetails += 'Currently stale on node ' + node;
            const currentlyStale = this.backendService.offsubnetStaleEndpointHistory(this.fabricName,this.vnid,this.address,'is_stale','endpoint') ;

            const staleHistory = this.backendService.offsubnetStaleEndpointHistory(this.fabricName,this.vnid,this.address,'is_stale','history') ;
            forkJoin([currentlyStale,staleHistory]).subscribe(
                (data)=>{
                    const is_stale = data[0]['objects'][0]['ept.endpoint'] ;
                    this.endpoint.is_stale = is_stale ;
                    if(is_stale) {
                        for(let item of data[1]['objects']) {
                            this.staleList.push(item['ept.history'].node) ;
                        }
                    }
                },
                (error)=>{
                    const msg = 'Could not check if the endpoint has stale nodes! ' + error['error']['error'] ;
                    this.modalService.setAndOpenModal('error','Error',msg,this.msgModal,false) ;
                }
            )

        }
        if (status === 'deleted') {
            this.endpointStatus = 'Not currently present in the fabric';
        } else {
            this.endpointStatus = `Local on node <strong>${node}</strong>`
            if(node > 0xffff) {
                const nodeA = (node & 0xffff0000) >> 16 ;
                const nodeB = (node & 0x0000ffff) ;
                this.endpointStatus = `Local on node <strong>(${nodeA},${nodeB})</strong>` ;
            }
            if (intf !== '') {
                this.endpointStatus += `, interface <strong>${intf}</strong>`;
            }
            if (encap !== '') {
                this.endpointStatus += `, encap <strong>${encap}</strong>`;
            }
        }
        this.fabricDetails = 'Fabric <strong>' + this.endpoint.fabric + '</strong>' ;
        if (this.endpoint.type === 'ipv4' || this.endpoint.type === 'ipv6') {
            this.fabricDetails += ', VRF <strong>' + vrfbd +'</strong>' ;
        } else {
            this.fabricDetails += ', BD <strong>' + vrfbd + '</strong>';
        }
        if (epgname !== '') {
            this.fabricDetails += ', EPG <strong>' + epgname + '</strong>' ;
        }
    }

    onClickOfDelete() {
        
        const msg = 'Are you sure you want to delete all information for ' + this.endpoint.addr + ' from the local database? Note, this will not affect the endpoint state within the fabric.'
        this.openModal('info','Wait',msg,this.msgModal,true,this.deleteEndpoint) ;
    }

    deleteEndpoint() {
        this.backendService.deleteEndpoint(this.fabricName, this.vnid, this.address).subscribe(
            (data) => {
                const msg = 'Endpoint deleted successfully' ;
                this.openModal('success','Success',msg,this.msgModal) ;
            },
            (error) => {
                const msg = 'Could not delete endpoint! ' + error['error']['error'] ;
                this.openModal('error','Error',msg,this.msgModal) ;
            }
        )
    }

    getEndpoint(fabric, vnid, address) {
        this.loading = true;
        this.backendService.getEndpoint(fabric, vnid, address).subscribe(
            (data) => {
                this.endpoint = data.objects[0]['ept.endpoint'];
                this.prefs.selectedEndpoint = this.endpoint;
                this.setupStatusAndInfoStrings();
                this.loading = false;
            },
            (error) => {
                const msg = 'Failed to load endpoint' ;
                this.openModal('error','Error',msg,this.msgModal) ;
            }
        );
    }

    public refresh() {
        this.backendService.dataplaneRefresh(this.fabricName, this.endpoint.vnid, this.endpoint.addr).subscribe(
            (data) => {
                const msg = 'Refresh successful' ;
                this.openModal('success','Success',msg,this.msgModal) ;
            },
            (error) => {
                const msg = 'Failed to refresh endpoint' ;
                this.openModal('error','Error',msg,this.msgModal) ;
            }
        ) 
    }

    onClickOfRefresh() {
        const msg = 
        'Are you sure you want to force a refresh of ' + this.address + '? This operation may take longer than expected' ;
        this.openModal('info','Wait',msg,this.msgModal,true,this.refresh) ;
    }

    public clearEndpoints() {
       console.log(this.clearNodes) ;
    }

    openModal(modalIcon,modalTitle,modalBody,modalRef:TemplateRef<any>,decisionBox = false,callback=undefined) {
        this.modalIcon = modalIcon ;
        this.modalTitle = modalTitle ;
        this.modalBody = modalBody ;
        this.decisionBox = decisionBox ;
        this.callback = callback ;
        this.modalService.openModal(modalRef) ;

    }

    runFunction() {
        this.callback() ;
    }

    onClickOfClear() {
        this.openModal('','','',this.clearModal) ;
    }

    onClearDropdownAdd(event) {
        console.log(this.clearEndpointOptions) ;
        if(event.label.toLowerCase() === 'select all') {
            this.clearEndpointOptions = [] ;
        }
    }

    onClearDropdownRemove(event) {
        if(event.label === 'Select All') {

        }
    }
}
