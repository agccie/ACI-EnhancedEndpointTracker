import {Injectable} from '@angular/core';
import {FabricSettings} from '../_model/fabric-settings';
import {Fabric} from '../_model/fabric';

@Injectable({
    providedIn: 'root'
})

export class PreferencesService {
    pageSize = 10;
    selectedEndpoint: any;
    fabricSettings: FabricSettings;
    fabric: Fabric;

    constructor() {
        this.fabricSettings = new FabricSettings();
        this.fabric = new Fabric();
    }

    getEndpointParams(context, callback) {
        context.activatedRoute.parent.parent.paramMap.subscribe(params => {
            const fabricName = params.get('fabric');
            if (fabricName != undefined) {
                context.activatedRoute.parent.paramMap.subscribe(params => {
                    const vnid = params.get('vnid');
                    const address = params.get('address');
                    this.getEndpoint(fabricName, vnid, address, context, callback);
                    context.loading = false;
                }, error => {
                    context.loading = false;
                });
            }
        }, error => {
            context.loading = false;
        });
    }

    getEndpoint(fabric, vnid, address, context, callback?) {
        context.loading = true;
        context.backendService.getEndpoint(fabric, vnid, address).subscribe(
            (data) => {
                this.selectedEndpoint = data.objects[0]['ept.endpoint'];
                context.endpoint = this.selectedEndpoint;
                if (callback !== undefined) {
                    callback();
                }
                context.loading = false;
            },
            (error) => {
                context.loading = false;
            }
        );
    }
}
