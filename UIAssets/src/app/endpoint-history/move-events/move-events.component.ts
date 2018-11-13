import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';

@Component({
  selector: 'app-move-events',
  templateUrl: './move-events.component.html',
  styleUrls: ['./move-events.component.css']
})
export class MoveEventsComponent implements OnInit {
  rows:any ;
  endpoint:any;
  loading=false;
  constructor(private bs:BackendService, private prefs:PreferencesService) {
    this.endpoint = this.prefs.selectedEndpoint ;
    this.getMoveEventsForEndpoint(this.endpoint.fabric,this.endpoint.vnid,this.endpoint.addr) ;
   }

  ngOnInit() {
  }

  getMoveEventsForEndpoint(fabric,vnid,address) {
    this.bs.getMoveEventsForEndpoint(fabric,vnid,address).subscribe(
      (data)=>{
        this.rows = data['objects'][0]['ept.move']['events'] ;
        
      },
      (error)=>{
        this.rows = [] ;
      }
    )
  }

}
