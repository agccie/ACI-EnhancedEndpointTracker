import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';
import { Router } from '../../../../node_modules/@angular/router';

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

  constructor(private backendService : BackendService, private prefs:PreferencesService, private router: Router) { 
    this.rows = [] ;
    this.endpoints = [] ;
    this.pageSize = this.prefs.pageSize ;
  }
  
  ngOnInit() {
    this.getEndpoints() ;
    
  }

  getEndpoints() {
    this.backendService.getEndpoints().subscribe(
      (data) => {
        console.log(data) ;
        this.rows = data['objects'] ;
        this.endpoints=data['objects'] ;
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
       console.log(error) ;
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
    if( ( value.events.length > 0 && value.events[0].rw_bd > 0 && value.events[0].rw_mac.length > 0 ) ||  (value.first_learn.rw_bd > 0 && value.first_learn.rw_mac.length > 0)) {
     address = value.events.length > 0 ?  value.events[0].rw_mac: value.first_learn.rw_mac ;
    }
    this.prefs.endpointDetailsObject = value ;
    this.router.navigate(["/ephistory",value.fabric,value.vnid,address]) ;

  }



}
