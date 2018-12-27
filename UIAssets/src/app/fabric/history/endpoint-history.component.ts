import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {PreferencesService} from '../../_service/preferences.service';
import {BackendService} from '../../_service/backend.service';
import {ActivatedRoute} from '@angular/router';
import {forkJoin} from 'rxjs';
import {ModalService} from '../../_service/modal.service';
import {EndpointList, Endpoint} from '../../_model/endpoint';

@Component({
    selector: 'app-endpoint-history',
    templateUrl: './endpoint-history.component.html'
})

export class EndpointHistoryComponent implements OnInit {
    loading = true;
    tabs: any = [];
    endpoint: Endpoint = new Endpoint;
    vnid: number = 0;
    address: string = "";
    fabricName: string = "";
    offsubnetNodeList = [];
    staleNodeList = [];
    xrNodeList = [];
    total_moves: number = 0;
    total_offsubnet: number = 0;
    total_stale: number = 0;
    total_rapid: number = 0;
    total_remediate: number = 0;

    clearEndpointOptions: any;
    clearNodes = [];

    dropdownActive = false;
    decisionBox = false;
    callback: any;
    @ViewChild('clearMsg') clearModal: TemplateRef<any>;

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
            {name: ' Rapid', path: 'rapid', icon: 'icon-too-fast'},
            {name: ' Off-Subnet', path: 'offsubnetevents', icon: 'icon-jump-out'},
            {name: ' Stale', path: 'staleevents', icon: 'icon-warning'},
            {name: ' Cleared', path: 'cleared', icon: 'icon-delete'}
        ];
    }

    ngOnInit() {
        this.activatedRoute.parent.paramMap.subscribe(params => {
            this.fabricName = params.get('fabric');
            if (this.fabricName !== undefined) {
                this.activatedRoute.paramMap.subscribe(params => {
                    this.vnid = parseInt(params.get('vnid')) || 0;
                    this.address = params.get('address');
                    this.getEndpoint(this.fabricName, this.vnid, this.address);
                });
            }
        });
    }

    getEndpoint(fabric, vnid, address) {
        this.loading = true;
        // need to get eptEndpoint info and merge in following other attributes:
        //  1) eptEndpoint state for this endpoint
        //  2) event counts (moves, offsubnet, stale, XR nodes)
        //  3) currently stale nodes and currently offsubnet nodes

        this.offsubnetNodeList = [];
        this.staleNodeList = [];
        this.xrNodeList = [];
        this.total_moves = 0;
        this.total_offsubnet = 0;
        this.total_stale = 0;
        this.total_rapid = 0;
        this.total_remediate = 0;

        const getEndpointState = this.backendService.getEndpoint(fabric, vnid, address);
        const getMoveCount = this.backendService.getCountsForEndpointDetails(fabric, vnid, address, 'move');
        const getOffsubnetCount = this.backendService.getCountsForEndpointDetails(fabric, vnid, address, 'offsubnet');
        const getStaleCount = this.backendService.getCountsForEndpointDetails(fabric, vnid, address, 'stale');
        const getRapidCount = this.backendService.getCountsForEndpointDetails(fabric, vnid, address, 'rapid');
        const getRemediateCount = this.backendService.getCountsForEndpointDetails(fabric, vnid, address, 'remediate');
        const getOffsubnetNodes = this.backendService.getCurrentlyOffsubnetNodes(fabric, vnid, address);
        const getStaleNodes = this.backendService.getCurrentlyStaleNodes(fabric, vnid, address);
        const getXrNodes = this.backendService.getActiveXrNodes(fabric, vnid, address);
        
        forkJoin(getEndpointState, getMoveCount, getOffsubnetCount, getStaleCount, getRapidCount, getRemediateCount, getOffsubnetNodes, getStaleNodes, getXrNodes).subscribe(
            ([endpointState, moveCount, offsubnetCount, staleCount, rapidCount, remediateCount, offsubnetNodes, staleNodes, xrNodes]) =>{
                let endpoint_list = new EndpointList(endpointState);
                if(endpoint_list.objects.length>0){
                    this.endpoint = endpoint_list.objects[0];
                    this.prefs.selectedEndpoint.init()
                    this.prefs.selectedEndpoint.sync(this.endpoint);
                }
                let move_count_list = new EndpointList(moveCount);
                let offsubnet_count_list = new EndpointList(offsubnetCount);
                let stale_count_list = new EndpointList(staleCount);
                let rapid_count_list = new EndpointList(rapidCount);
                let remediate_count_list = new EndpointList(remediateCount);
                let offsubnet_node_list = new EndpointList(offsubnetNodes);
                let stale_node_list = new EndpointList(staleNodes);
                let xr_node_list = new EndpointList(xrNodes);
                if(move_count_list.objects.length>0){
                    this.total_moves = move_count_list.objects[0].count;
                }
                if(offsubnet_count_list.objects.length>0){
                    this.total_offsubnet = 0;
                    //need to sum event count across all nodes
                    offsubnet_count_list.objects.forEach(element => {
                        this.total_offsubnet+= element.count;
                    });
                }
                if(stale_count_list.objects.length>0){
                    this.total_stale = 0;
                    //need to sum event count across all nodes
                    stale_count_list.objects.forEach(element => {
                        this.total_stale+= element.count;
                    });
                }
                if(rapid_count_list.objects.length>0){
                    this.total_rapid = rapid_count_list.objects[0].count;
                }
                if(remediate_count_list.objects.length>0){
                    this.total_remediate = 0;
                    //need to sum event count across all nodes
                    remediate_count_list.objects.forEach(element => {
                        this.total_remediate+= element.count;
                    })
                }
                if(offsubnet_node_list.objects.length>0){
                    //add each offsubnet node to offsubnetNodeList
                    this.offsubnetNodeList = [];
                    offsubnet_node_list.objects.forEach(element => {
                        if(element.node>0){
                            this.offsubnetNodeList.push(element.node);
                        }
                    })
                }
                if(stale_node_list.objects.length>0){
                    //add each stale node to offsubnetNodeList
                    this.staleNodeList = [];
                    stale_node_list.objects.forEach(element => {
                        if(element.node>0){
                            this.staleNodeList.push(element.node);
                        }
                    })
                }
                if(xr_node_list.objects.length>0){
                    //add each xr node to xrNodeList
                    this.xrNodeList = [];
                    xr_node_list.objects.forEach(element => {
                        if(element.node>0){
                            this.xrNodeList.push(element.node);
                        }
                    })
                }
                this.loading = false;
            }, 
            (error) => {
                this.loading = false;
                this.modalService.setModalError({
                    "body": 'Failed to load endpoint. ' + error['error']['error']
                })    
            }
        );
    }

    toggleXrNodeList(){
        //toggle displayXrNodes between true/false 
        this.prefs.displayXrNodes = !this.prefs.displayXrNodes;
    }

    /*
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
    */
}
