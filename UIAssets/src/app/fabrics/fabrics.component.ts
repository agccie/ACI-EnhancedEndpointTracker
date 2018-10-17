import { Component, OnInit,ViewChild } from '@angular/core';

@Component({
  selector: 'app-fabrics',
  templateUrl: './fabrics.component.html',
  styleUrls: ['./fabrics.component.css']
})
export class FabricsComponent implements OnInit {

  @ViewChild('myTable') table : any ;
  title = 'app';
  sorts:any ;
  rows:any ;
  tabs:any ;
  tabIndex = 0 ;
  expanded:any = {} ;
  events:any ;
  eventRows:any ;
  latestEvents:any ;
  endpointMoves:any ;
  subnetPoints:any ;
  staleEndpoints:any ;

  constructor(){
    this.sorts = { name:"fabric", dir:'asc'} ;
    this.rows = [{fabric:'Fabric1' , status:'Stopped', ips:'2300', macs:'2000', 
                 events:[{time:new Date() , status:'Initializing', description:'Connecting to APIC'},{time:new Date(), status:'Restarting' , description:'User triggered restart'}]}]
    this.tabs = [{name:'Latest Endpoint Events', active:true},{name:'Endpoint Moves',active:false},{name:'Off-Subnet Endpoints',active:false},{name:'Stale Endpoints',active:false}]
    this.latestEvents = [{time:new Date() , fabric:'Fabric1', type:'IP', address:'172.168.0.1',vrfbd:'uni/tn-2/ctx-213'},
                         {time:new Date() , fabric:'Fabric1', type:'MAC', address:'0C:09:A4:FF',vrfbd:'uni/tn-2/ctx-213'}] ;
    this.endpointMoves = [{time:new Date() , fabric:'Fabric1', type:'IP', address:'172.168.0.1',vrfbd:'uni/tn-2/ctx-214'},
                         {time:new Date() , fabric:'Fabric1', type:'MAC', address:'0C:09:A4:FF',vrfbd:'uni/tn-2/ctx-214'}] ;
    this.subnetPoints = [{time:new Date() , fabric:'Fabric1', type:'IP', address:'172.168.0.1',vrfbd:'uni/tn-2/ctx-214'},
                         {time:new Date() , fabric:'Fabric1', type:'MAC', address:'0C:09:A4:FF',vrfbd:'uni/tn-2/ctx-214'}] ;
    this.staleEndpoints = [{time:new Date() , fabric:'Fabric1', type:'IP', address:'172.168.0.1',vrfbd:'uni/tn-2/ctx-215'},
                          {time:new Date() , fabric:'Fabric1', type:'MAC', address:'0C:09:A4:FF',vrfbd:'uni/tn-2/ctx-215'}] ;
    this.events = [this.latestEvents,this.endpointMoves,this.subnetPoints,this.staleEndpoints] ;
    this.eventRows = this.events[0] ;
  }

  ngOnInit() {

  }

  changeTab(index){
    this.tabs[this.tabIndex].active = false;
    this.tabs[index].active = true ;
    this.tabIndex = index ;
    this.eventRows = this.events[index] ;
  }

  onToggle(event) {
    console.log(event) ;
  }

  toggleRow(row) {
    console.log(row) ;
    console.log(this.table) ;
    console.log(this.expanded) ;
    this.table.rowDetail.toggleExpandRow(row) ;
  }

}
