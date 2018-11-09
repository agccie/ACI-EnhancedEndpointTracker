import { Component, OnInit } from '@angular/core';
import { BackendService } from '../_service/backend.service';
import { PreferencesService } from '../_service/preferences.service';
import { ActivatedRoute } from '../../../node_modules/@angular/router';
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
  
  
  constructor(private bs:BackendService, public prefs:PreferencesService, private ar:ActivatedRoute) { 
    const fabric = ar.snapshot.params.fabric ;
    if(fabric === undefined) {
      this.getFabricSettingsList() ;
    }else{
      this.getFabricSettings(fabric,'default') ;
      this.prefs.fabric.fabric = fabric ;
    }
    console.log(fabric) ;
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
    this.modalBody = 'Are you sure you want to delete these settings ?'
    this.modalTitle = 'Confirmation' ;
    
  }

  deleteSettings() {

  }

  onSubmit() {
    
   this.removeUnsupportedFields() ;
    this.bs.updateFabric(this.prefs.fabric).subscribe(
      (data)=>{
      },
      (error)=>{

      }
    )
    this.bs.updateFabricSettings(this.prefs.fabricSettings).subscribe(
      (data) => {

      },
      (error) => {

      }
    )
  }

  removeUnsupportedFields() {
    if(this.prefs.fabricSettings.hasOwnProperty('dn')) {
      delete this.prefs.fabricSettings['dn'] ;
    }
    const fields = ['dn','event_count','controllers','events','auto_start'] ;
    for(let field of fields) {
      if(this.prefs.fabric.hasOwnProperty(field)) {
        delete this.prefs.fabric[field] ;
      }
    }
    
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
    this.bs.getFabric(fabricSettings.fabric).subscribe(
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
