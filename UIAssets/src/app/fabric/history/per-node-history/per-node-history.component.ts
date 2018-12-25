import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import {forkJoin} from 'rxjs';
import {ModalService} from '../../../_service/modal.service';
import {ActivatedRoute} from '@angular/router';
import {EndpointList, Endpoint, EndpointEvent} from '../../../_model/endpoint';

@Component({
    selector: 'app-per-node-history',
    templateUrl: './per-node-history.component.html',
})
export class PerNodeHistoryComponent implements OnInit {
    rows: EndpointEvent[] = [];
    endpoint: Endpoint = new Endpoint();
    loading: boolean = false;
    sorts = [{prop: 'ts', dir: 'desc'}];
    pageSize: number;

    constructor(private backendService: BackendService, private prefs: PreferencesService, 
                public modalService: ModalService, private activatedRoute: ActivatedRoute) {
        this.endpoint = this.prefs.selectedEndpoint;
        this.pageSize = this.prefs.pageSize;
        this.rows = [];
    }

    ngOnInit() {
        if (this.endpoint.addr.length>0){
            this.getPerNodeHistory()
        } else {
            this.loading = true;
            let that = this;
            this.prefs.getEndpointParams(this, function(fabricName, vnid, addr){
                that.endpoint.fabric = fabricName;
                that.endpoint.vnid = vnid;
                that.endpoint.addr = addr;
                that.getPerNodeHistory();
            })
        }
    }

    getPerNodeHistory(){
        this.loading = true;
        this.backendService.getEndpointHistoryAllNodes(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr).subscribe(
            (data)=>{
                let endpoint_list = new EndpointList(data);
                //need to combine endpoint events from all nodes, merging 'node' into each event
                let rows = []
                endpoint_list.objects.forEach(element => {
                    element.events.forEach(sub_element => {
                        sub_element.node = element.node;
                        rows.push(sub_element);
                    })
                })
                this.rows = rows;
                this.loading = false;
            }, 
            (error) =>{
                this.loading = false;
                this.modalService.setModalError({
                    "body": 'Failed to load endpoint detailed history. ' + error['error']['error']
                });             
            }
        );
    }

    /*
    getNodesForEndpoint() {
        let cumulativeEvents = [];
        let obsList = [];
        this.backendService.getNodesForOffsubnetEndpoints(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr, 'history').subscribe(
            (data) => {
                for (let items of data['objects']) {
                    let node = (items['ept.history']['node']);
                    obsList.push(this.backendService.getPerNodeHistory(this.endpoint.fabric, node, this.endpoint.vnid, this.endpoint.addr));
                }
                forkJoin(obsList).subscribe(
                    (data) => {
                        for (let item of data) {
                            for (let event of item['objects'][0]['ept.history']['events']) {
                                event.node = item['objects'][0]['ept.history']['node'];
                            }
                            cumulativeEvents = cumulativeEvents.concat(item['objects'][0]['ept.history']['events']);
                        }
                        this.rows = cumulativeEvents;
                    },
                    (error) => {
                        const msg = 'Could not fetch nodes for endpoint! ' + error['error']['error'];
                        //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal, false);
                    }
                )
            },
            (error) => {
                const msg = 'Could not fetch nodes for endpoint! ' + error['error']['error'];
                //this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal, false);
            }
        );
    }
    */
}
