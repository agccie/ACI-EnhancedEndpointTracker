import {Component, OnInit} from '@angular/core';
import {BackendService} from '../../_service/backend.service';
import {PreferencesService} from '../../_service/preferences.service';
import { forkJoin } from '../../../../node_modules/rxjs';

@Component({
    selector: 'app-per-node-history',
    templateUrl: './per-node-history.component.html',
    styleUrls: ['./per-node-history.component.css']
})
export class PerNodeHistoryComponent implements OnInit {
    rows: any;
    endpoint: any;
    loading = false;

    constructor(private bs: BackendService, private prefs: PreferencesService) {
        this.endpoint = this.prefs.selectedEndpoint;
        this.rows = [];
        this.getNodesForEndpoint(this.endpoint.fabric, this.endpoint.vnid,this.endpoint.addr) ;
        

    }

    ngOnInit() {
    }

    getNodesForEndpoint(fabric,vnid,address) {
        let cumulativeEvents = [] ;
        let obsList = [] ;
        this.bs.getNodesForOffsubnetEndpoints(fabric,vnid,address,'history').subscribe(
            (data) => {
                for(let items of data['objects']) {
                   let node = (items['ept.history']['node']) ;
                   obsList.push(this.bs.getPerNodeHistory(fabric,node,vnid,address)) ;
                }
                forkJoin(obsList).subscribe(
                    (data) => {
                        for(let item of data) {
                            for(let event of item['objects'][0]['ept.history']['events']){
                                event.node = item['objects'][0]['ept.history']['node'];
                            }
                            cumulativeEvents = cumulativeEvents.concat(item['objects'][0]['ept.history']['events']) ;
                        }
                        this.rows = cumulativeEvents ;
                    },
                    (error)=>{
                        debugger ;
                    }
                )
            } ,
            (error) => {

            }
        ) ;
        
    }

    getPerNodeHistory(fabric, node ,vnid, address,obj=[]) {
        

        this.bs.getPerNodeHistory(fabric, node, vnid, address).subscribe(
            (data) => {
                obj = obj.concat(data['objects'][0]['ept.history']['events']);
            },
            (error) => {
                console.log(error);
            }
        )
    }


}
