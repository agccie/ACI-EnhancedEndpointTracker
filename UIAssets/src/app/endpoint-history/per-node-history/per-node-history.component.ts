import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { ActivatedRoute } from '@angular/router';
import { PreferencesService } from '../../_service/preferences.service';

@Component({
  selector: 'app-per-node-history',
  templateUrl: './per-node-history.component.html',
  styleUrls: ['./per-node-history.component.css']
})
export class PerNodeHistoryComponent implements OnInit {
  rows:any ;
  endpoint:any;
  loading=false;
  constructor(private bs:BackendService, private prefs:PreferencesService) { 
    this.endpoint = this.prefs.selectedEndpoint ;
    this.rows = this.endpoint.events ;
  }

  ngOnInit() {
  }

  

}
