import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';
import { Router } from '@angular/router';

@Component({
  selector: 'app-stale-ept',
  templateUrl: './stale-ept.component.html',
  styleUrls: ['./stale-ept.component.css']
})
export class StaleEptComponent implements OnInit {
  rows:any ;
  pageSize:number ;
  count = 0 ;
  pageNumber=0; 
  loading = true ;
  sorts = [{prop:'ts',dir:'desc'}] ;
  constructor(private bs: BackendService, private prefs:PreferencesService, private router:Router) {
    this.pageSize = this.prefs.pageSize ;
   }

  ngOnInit() {
    this.getStaleEndpoints(0,this.sorts) ;
  }

  getStaleEndpoints(pageOffset=0,sorts=[]) {
    this.loading  = true ;
    this.bs.getFabricsOverviewTabData(pageOffset,sorts,'stale').subscribe(
      (data)=>{
        
        this.count = data['count'] ;
        this.rows = data['objects'] ;
        this.loading = false ;
      },
      (error)=>{
        console.log(error) ;
      }
    )
  }

  setPage(event) {
    this.pageNumber = event.offset ;
    this.getStaleEndpoints(event.offset,this.sorts) ;
  }

  onSort(event) {
    this.sorts = event.sorts ;
   this.getStaleEndpoints(this.pageNumber,event.sorts) ;
  }

  goToDetailsPage(value) {
    this.prefs.endpointDetailsObject = value ;
    this.router.navigate(["/ephistory",value.fabric,value.vnid,value.addr]) ;

  }

}
