import { Component, OnInit } from '@angular/core';

@Component({
  selector: 'app-per-node-history',
  templateUrl: './per-node-history.component.html',
  styleUrls: ['./per-node-history.component.css']
})
export class PerNodeHistoryComponent implements OnInit {
  rows:any ;
  constructor() { 
    this.rows=[{node:'101'}]
  }

  ngOnInit() {
  }

}
