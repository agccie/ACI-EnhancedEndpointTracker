import { Component, OnInit, ViewChild } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { Router } from '@angular/router';
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
        this.rows = data['objects'] ;
        let i=0 ;
        for(let fab of this.fabrics) {
          this.rows[i]['statLoad'] = true;
          this.rows[i]['macLoad'] = true;
          this.rows[i]['ipv4Load'] = true;
          this.rows[i]['ipv6Load'] = true;
          this.getFabricStatus(fab.fabric.fabric,i) ;
          this.getActiveMacAndIps(fab.fabric.fabric,'mac',i) ;
          this.getActiveMacAndIps(fab.fabric.fabric,'ipv4',i) ;
          this.getActiveMacAndIps(fab.fabric.fabric,'ipv6',i) ;
          i = i+1 ;
        }
        
        this.loading = false ;
      },
      (error)=> {

      }
    )
  }

  getActiveMacAndIps(fabricName, addressType, index) {
    this.rows[index][addressType +'Load'] = true ;
    this.bs.getActiveMacAndIps(fabricName,addressType).subscribe(
      (data)=>{
        if(data.hasOwnProperty('count')) {
        this.rows[index].fabric[addressType] = data['count'] ;
        this.rows[index][addressType +'Load'] = false ;
        
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

  

  getFabricStatus(fabricName,index) {
    this.rows[index]['statLoad'] = true ;
    this.bs.getFabricStatus(fabricName).subscribe(
      (data)=>{
        this.rows[index]['statLoad'] = false ;
        this.rows[index].fabric['status'] = data['status'] ;
      },
      (error)=>{

      }
    )
  }




}
