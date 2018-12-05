import { Component, OnInit, ViewChild, TemplateRef } from '@angular/core';
import { BackendService } from '../../../_service/backend.service';
import { PreferencesService } from '../../../_service/preferences.service';
import { ModalService } from '../../../_service/modal.service';
import { ActivatedRoute } from '../../../../../node_modules/@angular/router';

@Component({
  selector: 'app-cleared',
  templateUrl: './cleared.component.html',
})

export class ClearedComponent implements OnInit {
  endpoint:any ;
  rows:any ;
  loading=false;
  pageSize = 25 ;
  sorts = [{ prop:'events[0].ts' , dir:'desc'}] ;
  @ViewChild('errorMsg') msgModal : TemplateRef<any> ;
  constructor(private backendService:BackendService, private prefs: PreferencesService, public modalService:ModalService,private activatedRoute:ActivatedRoute) { 
    this.endpoint = this.prefs.selectedEndpoint ;
    this.rows = [] ;
    
  }

  ngOnInit() {
    if(this.endpoint === undefined) {
      this.prefs.getEndpointParams(this,'getClearedEndpoints') ;
    }else{
      this.getClearedEndpoints() ;
    }
  }

  getClearedEndpoints() {
    this.loading = true ;
    this.backendService.getClearedEndpoints(this.endpoint.fabric,this.endpoint.vnid,this.endpoint.addr).subscribe(
      (data) => {
          this.rows = [];
          for (let object of data.objects) {
              const endpoint = object["ept.remediate"];
              this.rows.push(endpoint);
          }
          this.loading = false;
      },
      (error) => {
          this.loading = false;
          const msg = 'Failed to load cleared endpoints! ' + error['error']['error'] ;
          this.modalService.setAndOpenModal('error','Error',msg,this.msgModal) ;
      }
  )
  }

}
