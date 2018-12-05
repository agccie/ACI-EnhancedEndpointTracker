import {Injectable} from '@angular/core';
import {FabricSettings} from '../_model/fabric-settings';
import {Fabric} from '../_model/fabric';
import { ActivatedRoute } from '../../../node_modules/@angular/router';

@Injectable({
    providedIn: 'root'
})

export class PreferencesService {
    pageSize = 10;
    selectedEndpoint:any;
    fabricSettings: FabricSettings;
    fabric: Fabric;

    constructor() {
        this.fabricSettings = new FabricSettings();
        this.fabric = new Fabric();
    }

    getEndpointParams(context,callback,decodeNodes = false) {
        context.activatedRoute.parent.parent.paramMap.subscribe(params => {
            const fabricName = params.get('fabric');
            if (fabricName != undefined) {
                context.activatedRoute.parent.paramMap.subscribe(params => {
                    const vnid = params.get('vnid');
                    const address = params.get('address');
                    this.getEndpoint(fabricName, vnid, address,context,callback);
                    context.loading = false;
                }, error => {
                    context.loading = false;
                });
            }
        }, error => {
            context.loading = false;
        });
    }

    getEndpoint(fabric, vnid, address,context,callback = undefined,decodeNodes = false) {
        context.loading = true;
        context.backendService.getEndpoint(fabric, vnid, address).subscribe(
            (data) => {
                this.selectedEndpoint = data.objects[0]['ept.endpoint'];
                context.endpoint = this.selectedEndpoint ;
                if(callback !== undefined) {
                    context[callback]() ;
                }
                context.loading = false;
            },
            (error) => {
                context.loading = false ;

            }
        );
    }

    decodeLocalNodes(endpoint) {
        for(let event of endpoint.events) {
            if(event.node > 0xffff){
            const nodeA = (event.node & 0xffff0000) >> 16;
            const nodeB = (event.node & 0x0000ffff);
            event['localNode'] = `(${nodeA},${nodeB})`;
            }else{
                event['localNode'] = '' ;
            }
        }
    }

}
