import { Component, OnInit, ViewChild } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { Router } from '../../../../node_modules/@angular/router';

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
  @ViewChild('myTable') table : any ;
  constructor(private bs : BackendService, private router : Router) { 
    this.sorts = {prop:'fabric'}
    this.rows = [] ;
    this.showFabricModal = false ;
    this.fabrics=[] ;
    this.fabricName='' ;
  }

  ngOnInit() {
    this.getFabrics() ;
  }

  onToggle(event) {
    console.log(event) ;
  }

  toggleRow(row) {
    console.log(row) ;
    console.log(this.table) ;
    this.table.rowDetail.toggleExpandRow(row) ;
  }

  getFabrics() {
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
      },
      (error)=> {

      }
    )
  }

  getActiveMacAndIps(fabricName, addressType, index) {
    this.bs.getActiveMacAndIps(fabricName,addressType).subscribe(
      (data)=>{
        if(data['objects'] !== undefined && data['objects'].length > 0) {
        this.fabrics[index].fabric[addressType] = data['objects'][0]['ept.endpoint']['addr'] ;
        this.rows = this.fabrics ;
        }
        console.log(this.fabrics) ;
      } ,
      (error)=>{
        console.log(error) ;
      }
    )
  }

  onFabricNameSubmit() {
    this.router.navigate(['/settings', this.fabricName]) ;
  }

}
