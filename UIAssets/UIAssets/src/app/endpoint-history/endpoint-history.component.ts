import { Component, OnInit } from '@angular/core';

@Component({
  selector: 'app-endpoint-history',
  templateUrl: './endpoint-history.component.html',
  styleUrls: ['./endpoint-history.component.css']
})
export class EndpointHistoryComponent implements OnInit {
  tabs:any ;
  constructor() {
    this.tabs = [{name:'Per Node History',icon:'icon-clock',path:'pernodehistory'},{name:'Move Events', path:'moveevents', icon:'icon-panel-shift-right'},{name:'Off-Subnet Events',path:'offsubnetevents', icon:'icon-jump-out'},{name:'Stale Events',path:'staleevents',icon:'icon-warning'}]
   }

  ngOnInit() {
  }

}
