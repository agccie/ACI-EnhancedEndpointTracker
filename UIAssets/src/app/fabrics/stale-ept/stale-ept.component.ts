import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';

@Component({
  selector: 'app-stale-ept',
  templateUrl: './stale-ept.component.html',
  styleUrls: ['./stale-ept.component.css']
})
export class StaleEptComponent implements OnInit {
  rows:any ;
  constructor(private bs: BackendService) { }

  ngOnInit() {
    this.getStaleEndpoints() ;
  }

  getStaleEndpoints() {
    this.bs.getStalePointsForFabrics().subscribe(
      (data)=>{
        this.rows = data['objects'] ;
      },
      (error)=>{

      }
    )
  }

}
