import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';

@Component({
  selector: 'app-endpoints',
  templateUrl: './endpoints.component.html',
  styleUrls: ['./endpoints.component.css']
})
export class EndpointsComponent implements OnInit {
  rows:any ;
  radioFilter:any ;

  constructor(private backendService : BackendService) { 
    this.rows = [] ;
  }
  
  ngOnInit() {
    this.getEndpoints() ;
    
  }

  getEndpoints() {
    this.backendService.getEndpoints().subscribe(
      (data) => {
        console.log(data) ;
        this.rows = data['objects'] ;
      } , (error) => {
        console.log(error) ;
      }
    ) ;
  }

  onClickOfRadio(event) {
    console.log(event) ;
    console.log(this.radioFilter) ;
  }



}
