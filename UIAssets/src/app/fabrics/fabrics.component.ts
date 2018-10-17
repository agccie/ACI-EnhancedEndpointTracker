import { Component, OnInit,ViewChild } from '@angular/core';

@Component({
  selector: 'app-fabrics',
  templateUrl: './fabrics.component.html',
  styleUrls: ['./fabrics.component.css']
})
export class FabricsComponent implements OnInit {

  
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
    this.tabs = [{name:'Fabrics',path:'fabric-overview'},{name:'Endpoints',path:'endpoints'},{name:'Latest Events',path:'latest-events'},{name:'Moves',path:'moves'},{name:'Off-subnet Endpoints',path:'offsubnet-endpoints'},{name:'Stale Endpoints', path:'stale-endpoints'}]
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



  

}
