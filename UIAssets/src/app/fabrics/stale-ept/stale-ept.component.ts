import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';

@Component({
  selector: 'app-stale-ept',
  templateUrl: './stale-ept.component.html',
  styleUrls: ['./stale-ept.component.css']
})
export class StaleEptComponent implements OnInit {
  rows:any ;
  pageSize:number ;
  constructor(private bs: BackendService, private prefs:PreferencesService) {
    this.pageSize = this.prefs.pageSize ;
   }

  ngOnInit() {
    this.getStaleEndpoints() ;
  }

  getStaleEndpoints() {
    this.bs.getStalePointsForFabrics().subscribe(
      (data)=>{
        this.rows = data['objects'] ;
      },
      (error)=>{

      }
    )
  }

}
