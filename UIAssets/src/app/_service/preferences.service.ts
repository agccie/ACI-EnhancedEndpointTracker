import {Injectable} from '@angular/core';
import {Endpoint} from "../_model/endpoint";

@Injectable({
    providedIn: 'root'
})

export class PreferencesService {
    pageSize = 25;
    displayXrNodes: boolean = false;
    selectedEndpoint: Endpoint = new Endpoint();
    userRole: number = 0;
    userName: string = "admin";

    constructor() {
        this.userName = localStorage.getItem("userName") || "admin";
        this.userRole = parseInt(localStorage.getItem('userRole')) || 0;
    }

    // trigger callback with fabricName, vnid, and address
    getEndpointParams(context, callback) {
        context.activatedRoute.parent.parent.paramMap.subscribe(
            (params) => {
                const fabricName = params.get('fabric');
                if (fabricName != undefined) {
                    context.activatedRoute.parent.paramMap.subscribe(
                        (params) => {
                            const vnid = params.get('vnid');
                            const address = params.get('address');
                            callback(fabricName, vnid, address);
                        }
                    )
                } 
            }
        )
    }
}
