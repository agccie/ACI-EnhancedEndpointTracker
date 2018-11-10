import { Component, OnInit } from '@angular/core';
import { PreferencesService } from '../../_service/preferences.service';

@Component({
  selector: 'app-remediation',
  templateUrl: './remediation.component.html',
  styleUrls: ['./remediation.component.css']
})
export class RemediationComponent implements OnInit {
  inputs=[] ;
  constructor(public prefs:PreferencesService) {
    this.inputs = [
      {name:'Auto clear stale Endpoints',model:'auto_clear_stale',type:'boolean'},
      {name:'Auto clear offsubnet endpoints',model:'auto_clear_offsubnet',type:'boolean'}
    ]
   }

  ngOnInit() {
  }

}
