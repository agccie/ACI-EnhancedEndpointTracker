import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';

@Component({
  selector: 'app-moves',
  templateUrl: './moves.component.html',
  styleUrls: ['./moves.component.css']
})
export class MovesComponent implements OnInit {
  rows:any ;
  constructor(private bs: BackendService) { }

  ngOnInit() {
    this.getMovesForFabric() ;
  }

  getMovesForFabric() {
    this.bs.getMovesForFabrics().subscribe(
      (data)=>{
        console.log(data['objects']) ;
        this.rows = data['objects'] ;
      } , 
    () => {

    }) ; 
  }

}
