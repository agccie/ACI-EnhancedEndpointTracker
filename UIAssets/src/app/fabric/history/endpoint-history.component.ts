import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {PreferencesService} from '../../_service/preferences.service';
import {BackendService} from '../../_service/backend.service';
import {ActivatedRoute, Router} from '@angular/router';
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

    clearNodes = [];
    clearNodesLoading: boolean = false;

    dropdownActive: boolean = false;
    @ViewChild('clearModal') clearModal: TemplateRef<any>;

    constructor(private prefs: PreferencesService, private router: Router, private backendService: BackendService,
                private activatedRoute: ActivatedRoute, public modalService: ModalService) {
        this.tabs = [
            {name: ' History', icon: 'icon-computer', path: 'history'},
            {name: ' Detailed', icon: 'icon-clock', path: 'detailed'},
            {name: ' Move', path: 'moves', icon: 'icon-panel-shift-right'},
            {name: ' Rapid', path: 'rapid', icon: 'icon-too-fast'},
            {name: ' OffSubnet', path: 'offsubnet', icon: 'icon-jump-out'},
            {name: ' Stale', path: 'stale', icon: 'icon-warning'},
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
                    this.getEndpoint();
                });
            }
        });
    }

    public refresh(){
        //trigger child component refresh as well
        this.getEndpoint();
    }
    
    getEndpoint() {
        this.loading = true;
        // need to get eptEndpoint info and merge in following other attributes:
        //  1) eptEndpoint state for this endpoint
        //  2) event counts (moves, offsubnet, stale, XR nodes)
        //  3) currently stale nodes and currently offsubnet nodes

        let fabric = this.fabricName;
        let vnid = this.vnid;
        let address = this.address;

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

    disableDropDown(){
        //need to tie this to blur (off-focus event)
        this.dropdownActive = false;
    }


    onDataplaneRefreshEndpoint(){
        // request to dataplane refresh of endpoint
        let that = this;
        const msg =
        'Are you sure you want to force a refresh of <strong>' + this.address +'</strong>? ' +
        'This operation will query the APIC for the most recent state of the endpoint and then update the local database. ' +
        'It may take a few moments for the updates to be seen.';
        this.modalService.setModalConfirm({
            "title": "Wait",
            "body": msg,
            "callback": function(){ that.dataplaneRefreshEndpoint();}
        });
    }

    dataplaneRefreshEndpoint(){
        const msg =
        'Are you sure you want to force a refresh of <strong>' + this.address +'</strong>? ' +
        'This operation will query the APIC for the most recent state of the endpoint and then update the local database. ' +
        'It may take a few moments for the updates to be seen.';   
        this.modalService.setModalConfirm({
            "title": "Wait",
            "body": msg,
            "loading": true
        });
        this.backendService.dataplaneRefresh(this.fabricName, this.vnid, this.address).subscribe(
            (data) => {
                this.modalService.hideModal();
                this.getEndpoint();
            },
            (error) => {
                this.modalService.setModalError({
                    "body": 'Failed to refresh endpoint. ' + error['error']['error']
                }) 
            }
        );
    }

    onDeleteEndpoint(){
        // request to delete endpoint events
        let that = this;
        const msg = 'Are you sure you want to delete all information for <strong>' + this.endpoint.addr + '</strong>' +
                    ' from the local database? Note, this will not affect the endpoint state within the fabric.'
        this.modalService.setModalConfirm({
            "title": "Wait",
            "body": msg,
            "callback": function(){ that.deleteEndpoint();}
        });
    }

    deleteEndpoint() {
        const msg = 'Are you sure you want to delete all information for <strong>' + this.endpoint.addr + '</strong>' +
        ' from the local database? Note, this will not affect the endpoint state within the fabric.'
        this.modalService.setModalInfo({
            "title": "Wait",
            "body": msg,
            "loading": true
        })
        this.backendService.deleteEndpoint(this.fabricName, this.vnid, this.address).subscribe(
            (data) => {
                this.modalService.hideModal();
                this.router.navigate(['/fabric', this.fabricName]);
            },
            (error) => {
                this.modalService.setModalError({
                    "body": 'Failed to delete endpoint. ' + error['error']['error']
                }) 
            }
        )
    }

    addClearNodes = (term) => {
        //add whatever user inputs for now, validation performed on submit.
        return {label: term, value: term};
    }

    onClearEndpoint() {
        this.clearNodes = [];
        this.clearNodesLoading = false;
        this.modalService.openModal(this.clearModal);
    }

    clearEndpoint(){
        let nodes = this.parseClearNodes();
        if(nodes.length>0){
            this.clearNodesLoading = true;
            this.backendService.clearEndpoint(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr, nodes).subscribe(
                (data)=>{
                    this.clearNodesLoading = false;
                    this.modalService.hideModal();
                    this.getEndpoint();
                },
                (error)=>{
                    this.clearNodesLoading = false;
                    this.modalService.setModalError({
                        "body": 'Failed to clear endpoint. ' + error['error']['error']
                    }) 
                }
            );
         
        }
    }

    private parseClearNodes(): number[]{
        const minNode = 101;
        const maxNode = 4096;
        let nodes = [];
        this.clearNodes.forEach(element => {
            element.split(",").forEach( val => {
                val = val.replace(/^[ ]*/g, "")
                val = val.replace(/[ ]*$/g, "")
                if(val.match(/^[0-9]+$/)!=null){
                    val = parseInt(val)
                    if(!nodes.includes(val)){ 
                        if(val>=minNode && val<=maxNode){
                            nodes.push(val) 
                        }
                    }
                } else if(val.match(/^[0-9]+[ ]*-[ ]*[0-9]+$/)!=null){
                    var val1 = parseInt(val.split("-")[0])
                    var val2 = parseInt(val.split("-")[1])
                    if(val1 > val2){
                        for(var i=val2; i<=val1; i++){ 
                            if(!nodes.includes(i)){ 
                                if(i>=minNode && i<=maxNode){
                                    nodes.push(i);
                                }
                            } 
                        }
                    } else {
                        for(var i=val1; i<=val2; i++){ 
                            if(!nodes.includes(i)){
                                if(i>=minNode && i<=maxNode){
                                    nodes.push(i);
                                }
                            } 
                        }
                    }
                }
            })
        })
        return nodes;
    }

    /*


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



    */
}
