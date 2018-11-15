import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';
import { Router } from '../../../../node_modules/@angular/router';

@Component({
  selector: 'app-local-learns',
  templateUrl: './local-learns.component.html',
  styleUrls: ['./local-learns.component.css']
})
export class LocalLearnsComponent implements OnInit {

  rows:any ;
  endpoint:any;
  loading=false;
  constructor(private bs:BackendService, private prefs:PreferencesService,private router:Router) { 
    this.endpoint = this.prefs.selectedEndpoint ;
    this.rows = this.endpoint.events ;
  }

  ngOnInit() {
  }

  goToDetailsPage() {
    const value = this.endpoint ;
    this.router.navigate(["/ephistory",value.fabric,value.vnid,value.events[0].rw_mac]) ;

  }
}
