import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {PreferencesService} from '../../../_service/preferences.service';
import {ModalService} from '../../../_service/modal.service';
import {ActivatedRoute} from '@angular/router';
import {EndpointList, Endpoint, EndpointEvent, EndpointMoveEvent} from '../../../_model/endpoint';

@Component({
    selector: 'app-move-events',
    templateUrl: './move-events.component.html',
})
export class MoveEventsComponent implements OnInit {
    rows: any[] = [];
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
            this.getMoveEventsForEndpoint();
        } else {
            this.loading = true;
            let that = this;
            this.prefs.getEndpointParams(this, function(fabricName, vnid, addr){
                that.endpoint.fabric = fabricName;
                that.endpoint.vnid = vnid;
                that.endpoint.addr = addr;
                that.getMoveEventsForEndpoint();
            })
        }
    }

    getMoveEventsForEndpoint() {
        this.loading = true;
        this.rows = [];
        this.backendService.getMoveEventsForEndpoint(this.endpoint.fabric, this.endpoint.vnid, this.endpoint.addr).subscribe(
            (data) => {
                let endpoint_list = new EndpointList(data);
                if(endpoint_list.objects.length>0){
                    // technically this is EndpointMoveEvent casted after reading the object data.
                    this.rows = endpoint_list.objects[0].events;
                }
                this.loading = false;
            },
            (error) => {
                this.loading = false;
                this.modalService.setModalError({
                    "body": 'Failed to load endpoint mmove history. ' + error['error']['error']
                });     
            }
        );
    }
}
