import { Component, OnInit } from '@angular/core';
import { PreferencesService } from '../_service/preferences.service';
import { IfStmt } from '@angular/compiler';
import { BackendService } from '../_service/backend.service';
import { ActivatedRoute, Router } from '@angular/router';

@Component({
  selector: 'app-endpoint-history',
  templateUrl: './endpoint-history.component.html',
  styleUrls: ['./endpoint-history.component.css']
})
export class EndpointHistoryComponent implements OnInit {
  tabs:any ;
  endpoint:any ;
  endpointStatus='';
  fabricDetails='';
  staleoffsubnetDetails = '' ;
  showModal = false;
  modalTitle = '' ;
  modalBody = '' ;
  fab:string ;
  vnid:string;
  address:string;
  clearEndpointOptions:any ;
  clearNodes = [] ;
  showClearModal = false ;
  showSuccessModal = false; 
  loading = true ;
  routeSubscription:any;

  constructor(private prefs:PreferencesService, private bs : BackendService, private activatedRoute:ActivatedRoute, private router:Router) {
    this.clearEndpointOptions = [
      {label:'Select all' , value:0},
      {label:'Offsubnet endpoints', value:1},
      {label:'Stale Endpoints',value:2}
    ]
    this.tabs = [
      {name:' Local Learns',icon:'icon-computer',path:'locallearns'},
      {name:' Per Node History',icon:'icon-clock',path:'pernodehistory'},
      {name: ' Move Events', path:'moveevents', icon:'icon-panel-shift-right'},
      {name:'  Off-Subnet Events',path:'offsubnetevents', icon:'icon-jump-out'},
      {name:' Stale Events',path:'staleevents',icon:'icon-warning'}
    ] ;
    
  }

  ngOnInit() {
    this.routeSubscription = this.activatedRoute.params.subscribe(
      (params)=>{
        this.address = params['address'] ;
        this.fab = params['fabric'] ;
        this.vnid = params['vnid'] ;
        this.getSingleEndpoint(this.fab,this.vnid,this.address) ;
      }
    )
  }

  getEventProperties(property) {
    if(this.endpoint.events.length > 0) {
      return this.endpoint.events[0][property] ;
    }else if(this.endpoint.hasOwnProperty('first_learn')) {
      return this.endpoint.first_learn[property] ;
    }else{
      return '' ;
    }
  }

  setupStatusAndInfoStrings() {
    const status = this.getEventProperties('status') ;
    const node = this.getEventProperties('node') ;
    const intf = this.getEventProperties('intf_name') ;
    const encap = this.getEventProperties('encap') ;
    const epgname = this.getEventProperties('epg_name') ;
    const vrfbd = this.getEventProperties('vnid_name') ;
    if(this.endpoint.is_offsubnet) {
      this.staleoffsubnetDetails += 'Currently offsubnet on node ' + node + '\n' ;
    }
    if(this.endpoint.is_stale) {
      this.staleoffsubnetDetails += 'Current stale on node ' + node  ;
      //query ept.endpoint filter on vnid,fabric,address,is_stale or is_offsubnet for finding out is stale or is offsubnet currently
      //for finding a list of stale offsubnet nodes query same on ept.hisotry
    }

    if(status  === 'deleted') {
      this.endpointStatus = 'Not currently present in the fabric' ;
    }else {
      this.endpointStatus = 'Local on node ' + node 
      if(intf !==''){
        this.endpointStatus += ', interface ' + intf ;
      }
      if(encap !== '') {
        this.endpointStatus += ', encap ' + encap ;
      }
      //rw_mac logic and vpc decoding here
      if(epgname !== '') {
        this.endpointStatus += ', epg ' + epgname
      }
    }

    this.fabricDetails = 'Fabric ' + this.endpoint.fabric ;
    if(this.endpoint.type === 'ipv4' || this.endpoint.type==='ipv6') {
      this.fabricDetails += ', VRF ' 
    }else{
      this.fabricDetails += ', BD ' ;
    }
    this.fabricDetails += vrfbd + ', VNID ' + this.endpoint.vnid ;
  }

  onClickOfDelete() {
    this.modalTitle = 'Warning' ;
    this.modalBody = 'Are you sure you want to delete all information for ' + this.endpoint.addr + ' from the local database? Note, this will not affect the endpoint state within the fabric.'
    this.showModal = true ;
  }

  deleteEndpoint() {
    this.showModal = false ;
    this.bs.deleteEndpoint(this.endpoint.fabric,this.endpoint.vnid,this.endpoint.addr).subscribe(
      (data) => {
        
        this.showModalOnScreen('success','Success','Endpoint deleted successfully!') ;
      },
      (error) => {

      }
    )

  }

  showModalOnScreen(type,modalTitle,modalBody) {
    if(type === 'clear') {

    }else if(type==='success'){
      this.showClearModal = false;
      this.showModal = false ;
      this.modalBody = modalBody ;
      this.modalTitle = modalTitle ;
      this.showSuccessModal = true ;
    }
    else{
      this.showClearModal = false;
      this.modalBody = modalBody ;
      this.modalTitle = modalTitle ;
      this.showModal = true ;
   
    }
  }

  hideModal() {
    this.modalTitle='' ;
    this.modalBody='';
    this.showModal = false ;
  }

  getSingleEndpoint(fabric,vnid,address) {
    this.loading = true ;
    this.bs.getSingleEndpoint(fabric,vnid,address).subscribe(
      (data)=>{
        this.endpoint = data['objects'][0]['ept.endpoint'] ;
        this.prefs.selectedEndpoint = this.endpoint;
        this.setupStatusAndInfoStrings() ;
        this.loading = false ;
        this.router.navigate(['/ephistory',fabric,vnid,address,'locallearns'])
      },
      (error)=>{
        console.log(error) ;
        this.loading = false ;
      }
    ) ;
  }

  refresh() {
    this.getSingleEndpoint(this.fab , this.vnid, this.address) ;
  }

  addNodes = (term) => {
    return {label: term, value: term};
  }


  public filterNodes(nodes): any[] {
    let newarr: any[] = [];
    if (nodes !== undefined) {
      for (let i = 0; i < nodes.length; i++) {
        if (typeof(nodes[i]) === 'string') {
          if (nodes[i] !== 'global') {
            if (nodes[i].includes(',')) {
              nodes[i] = nodes[i].replace(/\s/g, '');
              const csv = nodes[i].split(',');
              for (let j = 0; j < csv.length; j++) {
                if (csv[j].includes('-')) {
                  newarr = newarr.concat(this.getArrayForRange(csv[j]));
                }
              }
            } else if (nodes[i].includes('-')) {
              newarr = newarr.concat(this.getArrayForRange(nodes[i]));
            } else {
              newarr.push(nodes[i]);
            }
          } else {
            newarr.push(0);
          }
        }
      }
    }
    return newarr;
  }

  public getArrayForRange(range: string) {
    const r = range.split('-');
    const arr = [];
    r.sort();
    for (let i = parseInt(r[0], 10); i <= parseInt(r[1], 10); i++) {
      arr.push(i);
    }
    return arr;
  }

  public clearEndpoints() {
    return this.endpoint.type.toUpperCase()  ;
  }



}
