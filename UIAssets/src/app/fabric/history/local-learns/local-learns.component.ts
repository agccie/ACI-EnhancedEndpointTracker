import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import {ActivatedRoute} from '@angular/router';
import { ModalService } from 'src/app/_service/modal.service';
import {EndpointList, Endpoint, EndpointEvent} from '../../../_model/endpoint';

@Component({
    selector: 'app-local-learns',
    templateUrl: './local-learns.component.html',
})

export class LocalLearnsComponent implements OnInit {
    rows: EndpointEvent[] = [];
    endpoint: Endpoint = new Endpoint();
    loading: boolean = false;
    sorts = [{prop: 'ts', dir: 'desc'}];
    pageSize: number;

    constructor(private backendService: BackendService, private prefs: PreferencesService, 
                private modalService: ModalService, private activatedRoute: ActivatedRoute) {
        this.pageSize = this.prefs.pageSize;
        this.endpoint = this.prefs.selectedEndpoint;
        this.rows = [];
    }

    ngOnInit() {
        this.loading = true;
        let that = this;
        this.prefs.getEndpointParams(this, function(fabricName, vnid, addr){
            that.endpoint.fabric = fabricName;
            that.endpoint.vnid = vnid;
            that.endpoint.addr = addr;
            that.getLocalLearn();
        })
    }

    // public refresh that can be triggered by parent
    public refresh(){
        this.getLocalLearn();
    }

    getLocalLearn(){
        this.loading = true;
        this.rows = [];
        this.backendService.getEndpoint(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr).subscribe(
            (data) => {
                let endpoint_list = new EndpointList(data);
                if(endpoint_list.objects.length>0){
                    this.endpoint = endpoint_list.objects[0];
                    this.rows = endpoint_list.objects[0].events;
                }
                this.loading = false;
            },
            (error) =>{
                this.loading = false;
                this.modalService.setModalError({
                    "body": 'Failed to load endpoint. ' + error['error']['error']
                });
            }
        );
    }
}
