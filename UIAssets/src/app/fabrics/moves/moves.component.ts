import { Component, OnInit } from '@angular/core';
import { BackendService } from '../../_service/backend.service';
import { PreferencesService } from '../../_service/preferences.service';

@Component({
  selector: 'app-moves',
  templateUrl: './moves.component.html',
  styleUrls: ['./moves.component.css']
})
export class MovesComponent implements OnInit {
  rows:any ;
  pageSize:number ;
  constructor(private bs: BackendService,private prefs:PreferencesService) { 
    this.pageSize = this.prefs.pageSize ;
  }

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
