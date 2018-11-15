import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';
import { Router } from '@angular/router';

@Component({
  selector: 'app-endpoints',
  templateUrl: './endpoints.component.html',
  styleUrls: ['./endpoints.component.css']
})
export class EndpointsComponent implements OnInit {
  rows:any ;
  radioFilter:any ;
  osFilter = false;
  stFilter = false;
  endpoints:any ;
  pageSize:number ;
  count = 100 ;
  pageNumber=0; 
  sorts = [] ;
  loading = true ;

  constructor(private backendService : BackendService, private prefs:PreferencesService, private router: Router) { 
    this.rows = [] ;
    this.endpoints = [] ;
    this.pageSize = this.prefs.pageSize ;
  }
  
  ngOnInit() {
    this.getEndpoints(0) ;
    
  }

  getEndpoints(pageOffset = 0, sorts = []) {
    this.backendService.getEndpoints(pageOffset,sorts).subscribe(
      (data) => {
        this.count = data['count'] ;
        this.rows = data['objects'] ;
        this.endpoints=data['objects'] ;
        this.loading = false ;
      } , (error) => {
        console.log(error) ;
      }
    ) ;
  }

  onFilterToggle() {
   this.backendService.getFilteredEndpoints(this.osFilter,this.stFilter).subscribe(
     (data) => {
       this.rows = data['objects'] ;
     },
     (error)=>{
      let err = 'Failed to fetch filtered data' ; 
      if(error.hasOwnProperty('error') && error.error.hasOwnProperty('error')) {
        err = error['error']['error'] ;
       }
       console.log(err) ;
     }
   )
    
  }

  getRowClass(row) {
    if(row['ept.endpoint']['is_stale']) {
      return 'swatch swatch--statusblue' ;
    }
    if(row['ept.endpoint']['is_offsubnet']) {

    }
    if(row['ept.endpoint'].events.length > 0 && row['ept.endpoint'].events[0].status === 'deleted') {

    }
    
  }

  goToDetailsPage(value) {
    let address = value.addr ;
    this.prefs.endpointDetailsObject = value ;
    this.router.navigate(["/ephistory",value.fabric,value.vnid,address]) ;

  }

  setPage(event) {
    this.pageNumber = event.offset ;
    this.getEndpoints(event.offset,this.sorts) ;
  }

  onSort(event) {
    console.log(event.sorts) ;
    this.sorts = event.sorts ;
   this.getEndpoints(this.pageNumber,event.sorts) ;
  }



}
