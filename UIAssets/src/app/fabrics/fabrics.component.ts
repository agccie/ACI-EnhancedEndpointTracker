import { Component, OnInit,ViewChild } from '@angular/core';
import { BackendService } from '../_service/backend.service';
import { Router } from '../../../node_modules/@angular/router';

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
  showModal:boolean ;
  modalTitle:string ;
  modalBody:string;
  

  constructor(private bs: BackendService, private router: Router){
    this.sorts = { name:"fabric", dir:'asc'} ;
    this.rows = [{fabric:'Fabric1' , status:'Stopped', ips:'2300', macs:'2000', 
                 events:[{time:new Date() , status:'Initializing', description:'Connecting to APIC'},{time:new Date(), status:'Restarting' , description:'User triggered restart'}]}]
    this.tabs = [
    {name:'Fabrics',path:'fabric-overview'},
    {name:'Endpoints',path:'endpoints'},
    {name:'Latest Events',path:'latest-events'},
    {name:'Moves',path:'moves'},
    {name:'Off-subnet Endpoints',path:'offsubnet-endpoints'},
    {name:'Stale Endpoints', path:'stale-endpoints'}
    ] ;
    this.showModal = false ;
    this.modalBody='' ;
    this.modalTitle='' ;
    
  }

  ngOnInit() {
    this.getAppStatus() ;
  }

  getAppStatus() {
    this.bs.getAppStatus().subscribe(
      (data)=>{
        this.getAppManagerStatus() ;
      } ,
      (error)=>{
        this.modalTitle='Error';
        this.modalBody='The app could not be started';
        this.showModal = true;
      }
    )
  }

  getAppManagerStatus() {
    this.bs.getAppManagerStatus().subscribe(
      (data)=>{
        if(data['manager']['status'] === 'stopped') {
          this.modalBody = 'Thread managers not running' ;
          this.modalTitle='Error';
          this.showModal = true ;
        }
        this.router.navigate(['/fabrics','fabric-overview']) ;
      },
      (error)=>{
        this.modalTitle='Error';
        this.modalBody='Could not reach thread manager'
        this.showModal = true;
      }
    )
  }



  

}
