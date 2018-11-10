import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';
import { Router } from '../../../../node_modules/@angular/router';


@Component({
  selector: 'app-moves',
  templateUrl: './moves.component.html',
  styleUrls: ['./moves.component.css']
})
export class MovesComponent implements OnInit {
  rows:any ;
  pageSize:number ;
  count = 0 ;
  pageNumber=0; 
  sorts = [] ;
  loading = true ;
  constructor(private bs: BackendService,private prefs:PreferencesService, private router:Router) { 
    this.pageSize = this.prefs.pageSize ;
  }

  ngOnInit() {
    this.getMovesForFabric(0,[{prop:'ts',dir:'desc'}]) ;
  }

  getMovesForFabric(pageOffset=0,sorts=[]) {
    this.loading = true; 
    this.bs.getFabricsOverviewTabData(pageOffset,sorts,'move').subscribe(
      (data)=>{
        this.count = data['count'] ;
        this.rows = data['objects'] ;
        this.loading = false ;
      } , 
    (error) => {

    }) ; 
  }

  setPage(event) {
    this.pageNumber = event.offset ;
    this.getMovesForFabric(event.offset,this.sorts) ;
  }

  onSort(event) {
    this.sorts = event.sorts ;
   this.getMovesForFabric(this.pageNumber,event.sorts) ;
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
