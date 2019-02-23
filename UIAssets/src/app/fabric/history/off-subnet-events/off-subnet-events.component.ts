import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import {ModalService} from '../../../_service/modal.service';
import {ActivatedRoute} from '@angular/router';
import {EndpointList, Endpoint, EndpointEvent} from '../../../_model/endpoint';

@Component({
    selector: 'app-off-subnet-events',
    templateUrl: './off-subnet-events.component.html',
})
export class OffSubnetEventsComponent implements OnInit {
    rows: EndpointEvent[] = [];
    endpoint: Endpoint = new Endpoint();
    loading: boolean = false;
    sorts = [{prop: 'ts', dir: 'desc'}];
    pageSize: number;

    constructor(private backendService: BackendService, private prefs: PreferencesService, private activatedRoute: ActivatedRoute,
                public modalService: ModalService) {
        this.rows = [];
        this.pageSize = this.prefs.pageSize;
        this.endpoint = this.prefs.selectedEndpoint;
    }

    ngOnInit() {
        this.loading = true;
        let that = this;
        this.prefs.getEndpointParams(this, function(fabricName, vnid, addr){
            that.endpoint.fabric = fabricName;
            that.endpoint.vnid = vnid;
            that.endpoint.addr = addr;
            that.getOffSubnetEvents();
        })
    }

    // public refresh that can be triggered by parent
    public refresh(){
        this.getOffSubnetEvents();
    }

    getOffSubnetEvents() {
        this.loading = true;
        this.backendService.getOffSubnetEndpoints(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr).subscribe(
            (data) => {
                this.rows = [];
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
            (error) => {
                this.loading = false;
                this.modalService.setModalError({
                    "body": 'Failed to load endpoint offsubnet history. ' + error['error']['error']
                });      
            }
        )
    }
}
