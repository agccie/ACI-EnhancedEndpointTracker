import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';

@Component({
  selector: 'app-history',
  templateUrl: './history.component.html',
  styleUrls: ['./history.component.css']
})
export class HistoryComponent implements OnInit {
  rows:any ;
  constructor(private bs : BackendService) { }

  ngOnInit() {
      this.getLatestEventsForFabrics() ;
  }

  getLatestEventsForFabrics() {
    this.bs.getLatestEventsForFabrics().subscribe(
      (data)=>{
        
        this.rows = data['objects'] ;
      } , 
      (error)=>{
        console.log(error) ;
      })
  }

  

}
