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
      return this.http.get(this.baseUrl + '/ept/endpoint?filter=' + filterString + '&count=1') ;
   }

   getEndpoints() {
     return this.http.get(this.baseUrl + '/ept/endpoint?page-size=25') ;
   }

   getLatestEventsForFabrics() {
     return this.http.get(this.baseUrl + '/ept/history?page-size=25') ;
   }

   getMovesForFabrics() {
     return this.http.get(this.baseUrl + '/ept/move?page-size=25') ;
   }

   getOffsubnetPointsForFabrics() {
     return this.http.get(this.baseUrl + '/ept/offsubnet') ;
   }

   getFilteredEndpoints(offsubnetFilter, staleFilter) {
     return this.http.get(this.baseUrl + '/ept/endpoint?filter=and(eq("is_offsubnet","' + offsubnetFilter + '"),eq("is_stale","' + staleFilter + '"))&page-size=25') ;
   }

   getStalePointsForFabrics() {
     return this.http.get(this.baseUrl + '/ept/stale') ;
   }

   getSearchResults(address) {
     return this.http.get(this.baseUrl + '/ept/endpoint?filter=regex("addr","' + address + '")&page-size=15') ;
   }

   getSingleEndpoint(fabric,vnid,address) {
    return this.http.get(this.baseUrl + '/uni/fb-' + fabric + '/endpoint/vnid-' + vnid + '/addr-' + address ) ;
   }

   getMoveEventsForEndpoint(fabric,vnid,address) {
    return this.http.get(this.baseUrl + '/uni/fb-' + fabric + '/move/vnid-' + vnid + '/addr-' + address) ;
   }

   getNodesForOffsubnetEndpoints(fabric,vnid,address,tab) {
     return this.http.get(this.baseUrl + '/ept/' + tab + '?filter=and(eq("fabric","' + fabric +'"),eq("vnid",' + vnid +'),eq("addr","' + address +'"))&include=node') ;
   }



}
