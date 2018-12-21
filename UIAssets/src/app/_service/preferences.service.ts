import {Injectable} from '@angular/core';

@Injectable({
    providedIn: 'root'
})

export class PreferencesService {
    pageSize = 25;
    selectedEndpoint: any;
    userRole: number = 0;
    userName: string = "admin";

    constructor() {
        this.userName = localStorage.getItem("userName") || "admin";
        this.userRole = parseInt(localStorage.getItem('userRole')) || 0;
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
