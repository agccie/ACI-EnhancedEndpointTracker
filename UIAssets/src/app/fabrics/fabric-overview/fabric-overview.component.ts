import { Component, OnInit, ViewChild } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { Router } from '../../../../node_modules/@angular/router';
import { PreferencesService } from '../../_service/preferences.service';

@Component({
  selector: 'app-fabric-overview',
  templateUrl: './fabric-overview.component.html',
  styleUrls: ['./fabric-overview.component.css']
})
export class FabricOverviewComponent implements OnInit {
  rows:any ;
  sorts:any ;
  showFabricModal:boolean ;
  fabrics:any ;
  fabricName:string;
  pageSize:number ;
  loading = true ;
  @ViewChild('myTable') table : any ;
  constructor(private bs : BackendService, private router : Router, private prefs:PreferencesService) { 
    this.sorts = {prop:'fabric'}
    this.rows = [] ;
    this.showFabricModal = false ;
    this.fabrics=[] ;
    this.fabricName='' ;
    this.pageSize = this.prefs.pageSize ;
  }

  ngOnInit() {
    this.getFabrics() ;
  }

  toggleRow(row) {
    console.log(row) ;
    console.log(this.table) ;
    this.table.rowDetail.toggleExpandRow(row) ;
  }

  getFabrics() {
    this.loading = true ;
    this.bs.getFabrics().subscribe(
      (data)=>{
        this.fabrics = data['objects'] ;
        let i=0 ;
        for(let fab of this.fabrics) {
          this.getActiveMacAndIps(fab.fabric.fabric,'mac',i) ;
          this.getActiveMacAndIps(fab.fabric.fabric,'ipv4',i) ;
          this.getActiveMacAndIps(fab.fabric.fabric,'ipv6',i) ;
          i = i+1 ;
        }
        this.rows = data['objects'] ;
        this.loading = false ;
      },
      (error)=> {

      }
    )
  }

  getActiveMacAndIps(fabricName, addressType, index) {
    this.bs.getActiveMacAndIps(fabricName,addressType).subscribe(
      (data)=>{
        if(data.hasOwnProperty('count')) {
        this.fabrics[index].fabric[addressType] = data['count'] ;
        this.rows = this.fabrics ;
        }
      } ,
      (error)=>{
        console.log(error) ;
      }
    )
  }

  onFabricNameSubmit(fabric) {
    this.bs.createFabric(fabric).subscribe(
      (data)=>{
        this.router.navigate(['/settings', this.fabricName]) ;
      }) ;
    
  }

  startStopFabric(action,fabricName) {
    this.bs.startStopFabric(action,fabricName,'testing').subscribe(
      (data)=>{
        if(data['success'] === true) {
          console.log('success') ;
        }
      },
      (error) => {
        console.log(error) ;
      }
    )

  }

  deleteFabric(fabric) {
    this.bs.deleteFabric(fabric).subscribe(
      (data)=>{
        if(data['success'] === true) {
          console.log('success') ;
        }
      },
      (error)=>{
        console.log(error) ;
      }
    )
  }



}
