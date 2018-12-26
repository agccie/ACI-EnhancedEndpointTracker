import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import {ModalService} from '../../../_service/modal.service';
import {ActivatedRoute} from '@angular/router';
import {EndpointList, Endpoint, EndpointEvent} from '../../../_model/endpoint';

@Component({
    selector: 'app-rapid',
    templateUrl: './rapid.component.html',
})
export class RapidComponent implements OnInit {
    rows: EndpointEvent[] = [];
    endpoint: Endpoint = new Endpoint();
    loading: boolean = false;
    sorts = [{prop: 'ts', dir: 'desc'}];
    pageSize: number;

    constructor(private backendService: BackendService, private prefs: PreferencesService, private activatedRoute: ActivatedRoute,
                public modalService: ModalService) {
        this.endpoint = this.prefs.selectedEndpoint;
        this.pageSize = this.prefs.pageSize;
        this.rows = [];
    }

    ngOnInit() {
        if (this.endpoint.addr.length>0){
            this.getRapidEvents();
        } else {
            this.loading = true;
            let that = this;
            this.prefs.getEndpointParams(this, function(fabricName, vnid, addr){
                that.endpoint.fabric = fabricName;
                that.endpoint.vnid = vnid;
                that.endpoint.addr = addr;
                that.getRapidEvents();
            })
        }
    }

    getRapidEvents() {
        this.loading = true;
        this.backendService.getRapidEndpoints(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr).subscribe(
            (data) => {
                this.rows = [];
                let endpoint_list = new EndpointList(data);
                if(endpoint_list.objects.length>0){
                    this.rows = endpoint_list.objects[0].events;
                }
                this.loading = false;
            },
            (error) => {
                this.loading = false;
                this.modalService.setModalError({
                    "body": 'Failed to load endpoint rapid history. ' + error['error']['error']
                });  
            }
        )
    }
}
