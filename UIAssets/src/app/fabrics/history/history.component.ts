import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';

@Component({
  selector: 'app-history',
  templateUrl: './history.component.html',
  styleUrls: ['./history.component.css']
})
export class HistoryComponent implements OnInit {
  rows:any ;
  pageSize:number;
  loading = true ;
  constructor(private bs : BackendService, private prefs:PreferencesService) { 
    this.pageSize = this.prefs.pageSize ;
  }

  ngOnInit() {
      this.getLatestEventsForFabrics() ;
  }

  getLatestEventsForFabrics() {
    this.bs.getLatestEventsForFabrics().subscribe(
      (data)=>{
        this.loading = false ;
        this.rows = data['objects'] ;
      } , 
      (error)=>{
        console.log(error) ;
      })
  }

  

}
