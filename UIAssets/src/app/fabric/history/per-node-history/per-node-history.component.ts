import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import {ModalService} from '../../../_service/modal.service';
import {ActivatedRoute} from '@angular/router';
import {EndpointList, Endpoint, EndpointEvent} from '../../../_model/endpoint';

@Component({
    selector: 'app-per-node-history',
    templateUrl: './per-node-history.component.html',
})
export class PerNodeHistoryComponent implements OnInit {
    rows: EndpointEvent[] = [];
    fullData: EndpointEvent[] = [];
    endpoint: Endpoint = new Endpoint();
    loading: boolean = false;
    sorts = [{prop: 'ts', dir: 'desc'}];
    pageSize: number;

    constructor(private backendService: BackendService, private prefs: PreferencesService, 
                public modalService: ModalService, private activatedRoute: ActivatedRoute) {
        this.endpoint = this.prefs.selectedEndpoint;
        this.pageSize = this.prefs.pageSize;
        this.rows = [];
        this.fullData = [];
    }

    ngOnInit() {
        this.loading = true;
        let that = this;
        this.prefs.getEndpointParams(this, function(fabricName, vnid, addr){
            that.endpoint.fabric = fabricName;
            that.endpoint.vnid = vnid;
            that.endpoint.addr = addr;
            that.getPerNodeHistory();
        })
    }

    // public refresh that can be triggered by parent
    public refresh(){
        this.getPerNodeHistory();
    }

    getPerNodeHistory(){
        this.loading = true;
        this.rows = [];
        this.backendService.getEndpointHistoryAllNodes(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr).subscribe(
            (data)=>{
                let endpoint_list = new EndpointList(data);
                //need to combine endpoint events from all nodes, merging 'node' into each event
                let rows = []
                endpoint_list.objects.forEach(element => {
                    element.events.forEach(sub_element => {
                        sub_element.node = element.node;
                        sub_element.reporting_node = "node-"+sub_element.node;
                        rows.push(sub_element);
                    })
                })
                this.rows = rows;
                this.fullData = rows;
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

    updateFilter(event) {
        let interests = [
            "reporting_node",
            "status",
            "intf_name",
            "encap",
            "flags_string",
            "pctag",
            "remote_string",
            "rw_mac",
            "epg_name"
        ];
        //split search term into multiple terms separated by a space
        let values = event.target.value.toLowerCase().split(" ").filter(function(v){
            return v.length>0
        })
        if(values.length>0){
            this.rows = this.fullData.filter(function (row) {
                let match = false;
                interests.forEach(i=>{
                    if(i in row){
                        let v = (""+row[i]).toLocaleLowerCase();
                        values.forEach(val=>{
                            if(val.length>0 && v.includes(val)){
                                match = true;
                            }
                        })
                    }
                })
                return match;
            });
        } else {
            this.rows = this.fullData;
        }
    }
}
