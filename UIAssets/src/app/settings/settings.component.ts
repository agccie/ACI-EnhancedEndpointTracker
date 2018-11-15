import { Component, OnInit } from '@angular/core';
import { BackendService } from '../_service/backend.service';
import { PreferencesService } from '../_service/preferences.service';
import { ActivatedRoute, Router } from '@angular/router';
import { FabricSettings } from '../_model/fabric-settings';

@Component({
  selector: 'app-settings',
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.css']
})
export class SettingsComponent implements OnInit {
  settings:FabricSettings ;
  tabs=[] ;
  modalTitle='' ;
  modalBody='' ;
  showModal = false ;
  showConfirmationModal = false ;
  showError = true;
  showSelectionModal = false; 
  fabrics = [] ;
  fabric:any;
  
  constructor(private bs:BackendService, public prefs:PreferencesService, private ar:ActivatedRoute, private router:Router) { 
    this.fabric = ar.snapshot.params.fabric ;
    if(this.fabric === undefined) {
      this.getFabricSettingsList() ;
    }else{
      this.getFabricSettings(this.fabric,'default') ;
      this.getFabricConnectivitySettings(this.fabric) ;
      this.prefs.fabric.fabric = this.fabric ;
    }
    console.log(this.fabric) ;
    this.tabs = [
      {name:'Connectivity',path:'connectivity'},
      {name:'Notification',path:'notification'},
      {name:'Remediation',path:'remediation'},
      {name:'Advanced',path:'advanced'}
    ]

   
  }

  getFabricSettingsList() {
    this.bs.getAllFabricSettings().subscribe(
      (data)=>{
        this.fabrics = data['objects'] ;
        this.showSelectionModal = true;
        this.modalTitle='Select a fabric to configure' ;
      },
      (error)=>{

      }
    )
  }

  ngOnInit() {
  }

  getFabricSettings(fabric,settings) {
    this.bs.getFabricSettings(fabric,settings).subscribe(
      (data)=>{
        this.settings = data['objects'][0]['ept.settings'] ;
        this.prefs.fabricSettings = this.settings ;
      }
    )
  }

  onClickOfDelete() {
    this.showConfirmationModal = true ;
    this.showError = false ;
    this.modalBody = 'Are you sure you want to delete the fabric ? You cannot undo this later !' ;
    this.modalTitle = 'Confirmation' ;
    
  }

  deleteFabric(fabric) {
    this.bs.deleteFabric(fabric).subscribe(
      (data)=>{
        if(data['success'] === true) {
          this.hideModal() ;
          this.showModalOnScreen('warning','Fabric deleted successfully!','Success') ;
          this.router.navigate(['/fabrics','fabric-overview'])
        }
      },
      (error)=>{
        console.log(error) ;
      }
    )
  }

  hideModal() {
    this.showConfirmationModal = false ;
    this.showModal = false ;
    this.modalBody = ''
    this.modalTitle = '' ;
  }

  showModalOnScreen(type,modalBody,modalTitle) {
    if(type==='confirmation') {
      this.showConfirmationModal = true ;
      this.showError = false; 
    }else{
      this.showModal = true; 
      this.showError = false ;
    }
    this.modalBody = modalBody ;
    this.modalTitle = modalTitle ;
  }

  

  onSubmit() {
   
   
   let connSettings = {}       ;
   let otherSettings = new FabricSettings() ;
   
   for(let prop in this.prefs.fabric) {
      if(this.prefs.fabric[prop] !== undefined && (this.prefs.fabric[prop] !== '' || this.prefs.fabric[prop] !== 0)) {
        connSettings[prop] = this.prefs.fabric[prop] ;
      }
    }
    for(let prop in this.prefs.fabricSettings) {
      if(this.prefs.fabricSettings[prop] !== undefined && (this.prefs.fabricSettings[prop] !== '' || this.prefs.fabricSettings[prop] !== 0)) {
        otherSettings[prop] = this.prefs.fabricSettings[prop] ;
      }
    }
    if(otherSettings.hasOwnProperty('dn')) {
      delete otherSettings['dn'] ;
    }
    const fields = ['dn','event_count','controllers','events','auto_start'] ;
    for(let field of fields) {
      if(connSettings.hasOwnProperty(field)) {
        delete connSettings[field] ;
      }
    }
    this.bs.updateFabric(connSettings).subscribe(
      (data)=>{
      },
      (error)=>{

      }
    )
    this.bs.updateFabricSettings(otherSettings).subscribe(
      (data) => {

      },
      (error) => {

      }
    )
  }

  

 

  isSubmitDisabled() {
    let fabricFormValid = true ;
    let fabricSettingsFormValid = true ; 
    for(let prop in this.prefs.fabric) {
      if(this.prefs.fabric[prop] === undefined || this.prefs.fabric[prop] === '') {
        fabricFormValid = false ;
        break ;
      }
    }
    for(let prop in this.prefs.fabricSettings) {
      if(this.prefs.fabricSettings[prop] === undefined || this.prefs.fabricSettings[prop] === '') {
        fabricSettingsFormValid = false ;
        break ;
      }
    }
    return (fabricFormValid && fabricSettingsFormValid ) ;
  }

  onFabricSelect(fabricSettings) {
    this.prefs.fabricSettings = fabricSettings ;
    this.getFabricConnectivitySettings(fabricSettings.fabric) ;
  }

  getFabricConnectivitySettings(fabric:String){

    this.bs.getFabric(fabric).subscribe(
      (data) => {
        this.prefs.fabric = data['objects'][0]['fabric'] ;
        this.showSelectionModal = false ;
      },
      (error) => {
        console.log(error) ;
      }
    )
  }

}
