import { Injectable } from '@angular/core';
import { FabricSettings } from '../_model/fabric-settings';
import { Fabric } from '../_model/fabric';

@Injectable({
  providedIn: 'root'
})
export class PreferencesService {
  pageSize = 25 ;
  endpointDetailsObject:any ;
  selectedEndpoint={} ;
  cul=0 ;
  fabricSettings:FabricSettings ;
  fabric:Fabric ;
  checkedThreadStatus = false ;
  constructor() { 
    this.fabricSettings = new FabricSettings() ;
    this.fabric = new Fabric() ;
  }
}
