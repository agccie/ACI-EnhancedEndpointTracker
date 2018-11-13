import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';

@Component({
  selector: 'app-stale-events',
  templateUrl: './stale-events.component.html',
  styleUrls: ['./stale-events.component.css']
})
export class StaleEventsComponent implements OnInit {
  rows:any;
  endpoint:any;
  nodes = [] ;
  loading=false;
  constructor(private bs:BackendService,private prefs:PreferencesService) { 
    this.rows = [];
    this.endpoint = this.prefs.selectedEndpoint ;
    this.getNodesForStaleEndpoints(this.endpoint.fabric,this.endpoint.vnid,this.endpoint.addr) ;
  }

  ngOnInit() {
  }

  getNodesForStaleEndpoints(fabric,vnid,address) {
    this.bs.getNodesForOffsubnetEndpoints(fabric,vnid,address,'stale').subscribe(
      (data) => {
        for(let i of data['objects']) {
          this.nodes.push(i['ept.stale']['node']) ;
        }
      }
    );
  }

}
