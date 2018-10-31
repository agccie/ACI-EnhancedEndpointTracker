import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';

@Component({
  selector: 'app-offsubnet-ept',
  templateUrl: './offsubnet-ept.component.html',
  styleUrls: ['./offsubnet-ept.component.css']
})
export class OffsubnetEptComponent implements OnInit {
  rows:any ;
  pageSize:number ;
  constructor(private bs : BackendService, private prefs:PreferencesService) { 
    this.pageSize = this.prefs.pageSize ;
  }

  ngOnInit() {
    this.getOffsubnetPoints() ;
  }

  getOffsubnetPoints() {
    this.bs.getOffsubnetPointsForFabrics().subscribe(
      (data)=>{
        console.log(data) ;
        this.rows = data['objects'] ;
      },
      (error)=>{

      }
    )
  }

  

}
