import { Component, OnInit, ViewChild } from '@angular/core';

@Component({
  selector: 'app-fabric-overview',
  templateUrl: './fabric-overview.component.html',
  styleUrls: ['./fabric-overview.component.css']
})
export class FabricOverviewComponent implements OnInit {
  rows:any ;
  sorts:any ;
  @ViewChild('myTable') table : any ;
  constructor() { 
    this.sorts = {prop:'fabric'}
    this.rows = [{fabric:'Fabric1' , status:'Stopped', ips:'2300', macs:'2000', 
    events:[{time:new Date() , status:'Initializing', description:'Connecting to APIC'},{time:new Date(), status:'Restarting' , description:'User triggered restart'}]}]
  }

  ngOnInit() {
  }

  onToggle(event) {
    console.log(event) ;
  }

  toggleRow(row) {
    console.log(row) ;
    console.log(this.table) ;
    this.table.rowDetail.toggleExpandRow(row) ;
  }

}
