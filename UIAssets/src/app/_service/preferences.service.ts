import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class PreferencesService {
  pageSize = 25 ;
  endpointDetailsObject:any ;
  selectedEndpoint:any ;
  constructor() { }
}
