import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {PreferencesService} from '../../_service/preferences.service';
import {BackendService} from '../../_service/backend.service';
import {ActivatedRoute} from '@angular/router';
import {forkJoin} from 'rxjs';
import {ModalService} from '../../_service/modal.service';

@Component({
    selector: 'app-endpoint-history',
    templateUrl: './endpoint-history.component.html'
})

export class EndpointHistoryComponent implements OnInit {
    tabs: any;
    endpoint: any;
    endpointStatus = '';
    fabricDetails = '';
    staleoffsubnetDetails = '';
    fabricName: string;
    vnid: string;
    address: string;
    rw_mac = '';
    rw_bd = '';
    clearEndpointOptions: any;
    clearNodes = [];
    loading = true;
    dropdownActive = false;
    decisionBox = false;
    callback: any;
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;
    @ViewChild('clearMsg') clearModal: TemplateRef<any>;
    offsubnetList = [];
    staleList = [];
    counts = [];
    addNodes = (term) => {
        return {label: term, value: term};
    };

    constructor(private prefs: PreferencesService, private backendService: BackendService,
                private activatedRoute: ActivatedRoute, public modalService: ModalService) {
        this.clearEndpointOptions = [
            {label: 'Select all', value: 0},
            {label: 'Offsubnet endpoints', value: 1},
            {label: 'Stale Endpoints', value: 2}
        ];
        this.tabs = [
            {name: ' History', icon: 'icon-computer', path: 'locallearns'},
            {name: ' Detailed', icon: 'icon-clock', path: 'pernodehistory'},
            {name: ' Move', path: 'moveevents', icon: 'icon-panel-shift-right'},
            {name: ' Off-Subnet', path: 'offsubnetevents', icon: 'icon-jump-out'},
            {name: ' Stale', path: 'staleevents', icon: 'icon-warning'},
            {name: ' Rapid', path: 'rapid', icon: 'icon-too-fast'},
            {name: ' Cleared', path: 'cleared', icon: 'icon-delete'}
        ];
    }

    ngOnInit() {
        this.loading = true;
        this.activatedRoute.parent.paramMap.subscribe(params => {
            this.fabricName = params.get('fabric');
            if (this.fabricName !== undefined) {
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

    getEndpoint(fabric, vnid, address) {
        this.loading = true;
        this.backendService.getEndpoint(fabric, vnid, address).subscribe(
            (data) => {
                this.endpoint = data.objects[0]['ept.endpoint'];
                this.prefs.selectedEndpoint = this.endpoint;
                this.setupStatusAndInfoStrings();
                this.getCounts();
                this.loading = false;
            },
            (error) => {
                this.loading = false;
                const msg = 'Failed to load endpoint! ' + error['error']['error'];
                //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        );
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
        const mac = this.getEventProperties('rw_mac');
        const mac_bd = this.getEventProperties('rw_bd');
        if (mac != '' && mac_bd != '') {
            this.rw_mac = mac;
            this.rw_bd = mac_bd;
        }
        this.staleoffsubnetDetails = '';
        if (this.endpoint.is_offsubnet) {
            this.staleoffsubnetDetails += 'Currently offsubnet on node ' + node + '\n';
            const currentlyOffsubnet = this.backendService.offsubnetStaleEndpointHistory(this.fabricName, this.vnid, this.address, 'is_offsubnet', 'endpoint');
            const offsubnetHistory = this.backendService.offsubnetStaleEndpointHistory(this.fabricName, this.vnid, this.address, 'is_offsubnet', 'history');
            forkJoin(currentlyOffsubnet, offsubnetHistory).subscribe(
                (data) => {
                    const is_offsubnet = data[0]['objects'][0]['ept.endpoint']['is_offsubnet'];
                    this.endpoint.is_offsubnet = is_offsubnet;
                    if (is_offsubnet) {
                        for (let item of data[1]['objects']) {
                            this.offsubnetList.push(item['ept.history'].node);
                        }
                    }
                },
                (error) => {
                    const msg = 'Could not check if the endpoint has offsubnet nodes! ' + error['error']['error'];
                    //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal, false);
                }
            )
        }
        if (this.endpoint.is_stale) {
            this.staleoffsubnetDetails += 'Currently stale on node ' + node;
            const currentlyStale = this.backendService.offsubnetStaleEndpointHistory(this.fabricName, this.vnid, this.address, 'is_stale', 'endpoint');
            const staleHistory = this.backendService.offsubnetStaleEndpointHistory(this.fabricName, this.vnid, this.address, 'is_stale', 'history');
            forkJoin([currentlyStale, staleHistory]).subscribe(
                (data) => {
                    const is_stale = data[0]['objects'][0]['ept.endpoint'];
                    this.endpoint.is_stale = is_stale;
                    if (is_stale) {
                        for (const item of data[1]['objects']) {
                            this.staleList.push(item['ept.history'].node);
                        }
                    }
                },
                (error) => {
                    const msg = 'Could not check if the endpoint has stale nodes! ' + error['error']['error'];
                    //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal, false);
                }
            )

        }
        if (status === 'deleted') {
            this.endpointStatus = 'Not currently present in the fabric';
        } else {
            const pod = this.getEventProperties('pod');
            this.endpointStatus = `Local on pod <strong>${pod}</strong> node <strong>${node}</strong>`;
            if (node > 0xffff) {
                const nodeA = (node & 0xffff0000) >> 16;
                const nodeB = (node & 0x0000ffff);
                this.endpointStatus = `Local on pod <strong>${pod}</strong> node <strong>(${nodeA},${nodeB})</strong>`;
            }
            if (intf !== '') {
                this.endpointStatus += `, interface <strong>${intf}</strong>`;
            }
            if (encap !== '') {
                this.endpointStatus += `, encap <strong>${encap}</strong>`;
            }
        }
        this.fabricDetails = 'Fabric <strong>' + this.endpoint.fabric + '</strong>';
        if (this.endpoint.type === 'ipv4' || this.endpoint.type === 'ipv6') {
            this.fabricDetails += ', VRF <strong>' + vrfbd + '</strong>';
        } else {
            this.fabricDetails += ', BD <strong>' + vrfbd + '</strong>';
        }
        if (epgname !== '') {
            this.fabricDetails += ', EPG <strong>' + epgname + '</strong>';
        }
    }

    onClickOfDelete() {
        const msg = 'Are you sure you want to delete all information for ' + this.endpoint.addr + ' from the local database? Note, this will not affect the endpoint state within the fabric.'
        //this.modalService.setAndOpenModal('info', 'Wait', msg, this.msgModal, true, this.deleteEndpoint, this);
    }

    deleteEndpoint() {
        this.backendService.deleteEndpoint(this.fabricName, this.vnid, this.address).subscribe(
            (data) => {
                this.modalService.hideModal();
                const msg = 'Endpoint deleted successfully';
                //this.modalService.setAndOpenModal('success', 'Success', msg, this.msgModal);
            },
            (error) => {
                this.modalService.hideModal();
                const msg = 'Could not delete endpoint! ' + error['error']['error'];
                //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        )
    }

    public refresh() {
        this.backendService.dataplaneRefresh(this.fabricName, this.endpoint.vnid, this.endpoint.addr).subscribe(
            (data) => {
                if (data['success']) {
                    this.modalService.hideModal();
                    const msg = 'Refresh successful';
                    //this.modalService.setAndOpenModal('success', 'Success', msg, this.msgModal);
                } else {
                    const msg = 'Failed to refresh endpoint';
                    //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
                }
            },
            (error) => {
                const msg = 'Failed to refresh endpoint';
                //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        );
    }

    onClickOfRefresh() {
        const msg =
            'Are you sure you want to force a refresh of ' + this.address +
            '? This operation will query the APIC for the most recent state of the endpoint and then update the local database.' +
            'It may take a few moments for the updates to be seen.';
        //this.modalService.setAndOpenModal('info', 'Wait', msg, this.msgModal, true, this.refresh, this);
    }

    public clearEndpoints() {
        let nodesList = this.filterNodes(this.clearNodes);
        if (this.endpoint.is_offsubnet) {
            nodesList = nodesList.concat(this.offsubnetList);
        }
        if (this.endpoint.is_stale) {
            nodesList = nodesList.concat(this.staleList);
        }
        this.modalService.hideModal();
        this.backendService.clearNodes(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr, nodesList).subscribe(
            (data) => {
                if (data['success']) {
                    const msg = 'Refresh successful';
                    //this.modalService.setAndOpenModal('success', 'Success', msg, this.msgModal);
                } else {
                    const msg = 'Failed to refresh endpoint';
                    //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
                }
            },
            (error) => {
                const msg = 'Failed to clear nodes! ' + error['error']['error'];
                //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        )
    }

    runFunction() {
        this.callback();
    }

    onClickOfClear() {
        //this.modalService.setAndOpenModal('', '', '', this.clearModal);
    }

    public filterNodes(nodes): any[] {
        let newarr: any[] = [];
        if (nodes !== undefined) {
            for (let i = 0; i < nodes.length; i++) {
                if (typeof(nodes[i]) === 'string') {
                    if (nodes[i].includes(',')) {
                        nodes[i] = nodes[i].replace(/\s/g, '');
                        const csv = nodes[i].split(',');
                        for (let j = 0; j < csv.length; j++) {
                            if (csv[j].includes('-')) {
                                newarr = newarr.concat(this.getArrayForRange(csv[j]));
                            } else {
                                const node = parseInt(csv[j], 10);
                                if (!isNaN(node)) {
                                    newarr.push(node);
                                }
                            }
                        }
                    } else if (nodes[i].includes('-')) {
                        newarr = newarr.concat(this.getArrayForRange(nodes[i]));
                    } else {
                        newarr.push(nodes[i]);
                    }
                }
            }
        }
        return newarr;
    }

    public getArrayForRange(range: string) {
        const r = range.split('-');
        const arr = [];
        r.sort();
        for (let i = parseInt(r[0], 10); i <= parseInt(r[1], 10); i++) {
            arr.push(i);
        }
        return arr;
    }

    public getCounts() {
        const obsList = [];
        for (const table of ['move', 'offsubnet', 'stale', 'rapid']) {
            obsList.push(this.backendService.getCountsForEndpointDetails(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr, table));
        }
        obsList.push(this.backendService.getXrNodesCount(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr));
        forkJoin(obsList).subscribe(
            (data) => {
                this.counts = [
                    {prop: 'Moves', ct: data[0]['count']},
                    {prop: 'Offsubnet', ct: data[1]['count']},
                    {prop: 'Stale', ct: data[2]['count']},
                    {prop: 'Rapid', ct: data[3]['count']}
                ];
                this.counts.push({prop: 'XR nodes', ct: data[4]['count']});
            },
            (error) => {
                const msg = 'Could not fetch counts! ' + error['error']['error'];
                //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        );
    }
}
