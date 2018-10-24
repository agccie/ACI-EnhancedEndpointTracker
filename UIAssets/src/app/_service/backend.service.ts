import { Injectable } from '@angular/core';
import {HttpClient} from '@angular/common/http' ;
import {interval as observableInterval, Observable, of as observableOf, throwError} from 'rxjs';
import {concat, delay, map, mergeMap, retryWhen, switchMap, take, filter} from 'rxjs/operators';


@Injectable({
  providedIn: 'root'
})
export class BackendService {
  baseUrl:any;
  domain:any;
  constructor(private http: HttpClient) {
    this.domain='http://esc-aci-compute:9080' ;
    this.baseUrl = this.domain + '/api' ;
   }

   getAppStatus() {
     return this.http.get(this.baseUrl + '/app-status' ) ;
   }

   getAppManagerStatus() {
     return this.http.get(this.baseUrl + '/app-status/manager') ;
   }

   getFabrics() {
      return this.http.get(this.baseUrl + '/fabric') ;
   }

   getActiveMacAndIps(fabricName, addressType) {
      const filterString = 'and(eq("fabric","' + fabricName + '"),eq("type","' + addressType + '"),neq("events.0.status","deleted"))' ;
      return this.http.get(this.baseUrl + '/ept/endpoint?filter=' + filterString) ;
   }

   getEndpoints() {
     return this.http.get(this.baseUrl + '/ept/endpoint') ;
   }

   getLatestEventsForFabrics() {
     return this.http.get(this.baseUrl + '/ept/history') ;
   }

   getMovesForFabrics() {
     return this.http.get(this.baseUrl + '/ept/move') ;
   }

   getOffsubnetPointsForFabrics() {
     return this.http.get(this.baseUrl + '/ept/offsubnet') ;
   }

   getStalePointsForFabrics() {
     return this.http.get(this.baseUrl + '/ept/stale') ;
   }



}
