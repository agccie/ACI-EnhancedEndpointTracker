import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';
import { Router } from '@angular/router';

@Component({
  selector: 'app-history',
  templateUrl: './history.component.html',
  styleUrls: ['./history.component.css']
})
export class HistoryComponent implements OnInit {
  rows:any ;
  pageSize:number;
  count = 100 ;
  pageNumber=0; 
  sorts = [] ;
  loading = true ;

  constructor(private bs : BackendService, private prefs:PreferencesService, private router: Router) { 
    this.pageSize = this.prefs.pageSize ;
  }

  ngOnInit() {
      this.getLatestEventsForFabrics() ;
  }

  getLatestEventsForFabrics(pageOffset=0,sorts=[]) {
    this.bs.getFabricsOverviewTabData(pageOffset,sorts,'history').subscribe(
      (data)=>{
        this.loading = false ;
        this.count = data['count'] ;
        this.rows = data['objects'] ;
      } , 
      (error)=>{
        console.log(error) ;
      })
  }

  setPage(event) {
    this.pageNumber = event.offset ;
    this.getLatestEventsForFabrics(event.offset,this.sorts) ;
  }

  onSort(event) {
    console.log(event.sorts) ;
    this.sorts = event.sorts ;
   this.getLatestEventsForFabrics(this.pageNumber,event.sorts) ;
  }

  goToDetailsPage(val) {
    this.router.navigate(["/ephistory",val.fabric,val.vnid,val.addr]) ;

  }

  

}
