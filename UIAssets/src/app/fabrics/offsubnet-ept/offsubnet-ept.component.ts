import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';
import { Router } from '@angular/router';

@Component({
  selector: 'app-offsubnet-ept',
  templateUrl: './offsubnet-ept.component.html',
  styleUrls: ['./offsubnet-ept.component.css']
})
export class OffsubnetEptComponent implements OnInit {
  rows:any ;
  pageSize:number ;
  count = 0 ;
  pageNumber=0; 
  sorts = [] ;
  loading = true ;
  constructor(private bs : BackendService, private prefs:PreferencesService,private router:Router) { 
    this.pageSize = this.prefs.pageSize ;
  }

  ngOnInit() {
    this.getOffsubnetPoints(0,[{prop:'ts',dir:'desc'}]) ;
  }

  getOffsubnetPoints(pageOffset=0,sorts=[]) {
    this.loading = true ;
    this.bs.getFabricsOverviewTabData(pageOffset,sorts,'offsubnet').subscribe(
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
    this.getOffsubnetPoints(event.offset,this.sorts) ;
  }

  onSort(event) {
    this.sorts = event.sorts ;
   this.getOffsubnetPoints(this.pageNumber,event.sorts) ;
  }

  goToDetailsPage(value) {
    this.prefs.endpointDetailsObject = value ;
    this.router.navigate(["/ephistory",value.fabric,value.vnid,value.address]) ;

  }

  

}
