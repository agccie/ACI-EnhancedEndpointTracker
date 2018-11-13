import { Component, OnInit } from '@angular/core';
import { PreferencesService } from '../../_service/preferences.service';

@Component({
  selector: 'app-connectivity',
  templateUrl: './connectivity.component.html',
  styleUrls: ['./connectivity.component.css']
})
export class ConnectivityComponent implements OnInit {
  inputs=[];
  constructor(public prefs:PreferencesService) { 
    this.inputs = [
      {name:'Hostname', model:'apic_hostname'},
      {name:'APIC Certificate',model:'apic_cert'},
      {name:'Username', model:'apic_username'},
      {name:'Password',model:'apic_password'},
      {name:'SSH Username',model:'ssh_username'},
      {name:'SSH Password', model:'ssh_password'}
    ]
  }

  ngOnInit() {
  }

}
