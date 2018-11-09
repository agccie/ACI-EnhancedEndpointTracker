import { Injectable } from '@angular/core';
import {HttpClient,HttpParams} from '@angular/common/http' ;
import {interval as observableInterval, Observable, of as observableOf, throwError} from 'rxjs';
import {concat, delay, map, mergeMap, retryWhen, switchMap, take, filter} from 'rxjs/operators';
import {environment} from '../../environments/environment' ;
import { FabricSettings } from '../_model/fabric-settings';
import {User,UserList} from '../_model/user' ;


@Injectable({
  providedIn: 'root'
})
export class BackendService {
  baseUrl:any;
  domain:any;
  constructor(private http: HttpClient) {
    this.domain='http://esc-aci-compute:9080' ;
    this.baseUrl = this.domain + environment.api_entry ;
   }

   getAppStatus() {
     return this.http.get(this.baseUrl + '/app-status' ) ;
   }

   getAppManagerStatus() {
     return this.http.get(this.baseUrl + '/app-status/manager',{withCredentials:true}) ;
   }

   getFabrics() {
      return this.http.get(this.baseUrl + '/fabric') ;
   }

   getActiveMacAndIps(fabricName, addressType) {
      const filterString = 'and(eq("fabric","' + fabricName + '"),eq("type","' + addressType + '"),neq("events.0.status","deleted"))' ;
      return this.http.get(this.baseUrl + '/ept/endpoint?filter=' + filterString + '&count=1') ;
   }
   //May remove this and make the getFabricsOverview function as a single API call
   getEndpoints(pageOffset,sorts) {
     if(sorts.length===0) {
     return this.http.get(this.baseUrl + '/ept/endpoint?sort=fabric&page-size=25&page=' + pageOffset) ;
     }else{
      const sortsStr = this.getSortsArrayAsString(sorts) ;
       return this.http.get(this.baseUrl + '/ept/endpoint?sort='+sortsStr+'&page-size=25&page=' + pageOffset);
     }
   }

   getFabricsOverviewTabData(pageOffset,sorts,tab = 'endpoint') {
    if(sorts.length===0) {
    return this.http.get(this.baseUrl + '/ept/' + tab + '?sort=fabric&page-size=25&page=' + pageOffset) ;
    }else{
     const sortsStr = this.getSortsArrayAsString(sorts) ;
      return this.http.get(this.baseUrl + '/ept/' + tab + '?sort='+sortsStr+'&page-size=25&page=' + pageOffset);
    }
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
     return this.http.get(this.baseUrl + '/ept/endpoint?filter=and(eq("is_offsubnet",' + offsubnetFilter + '),eq("is_stale",' + staleFilter + '))&page-size=25') ;
   }

   getStalePointsForFabrics() {
     return this.http.get(this.baseUrl + '/ept/stale') ;
   }

   getSearchResults(address) {
     return this.http.get(this.baseUrl + '/ept/endpoint?filter=regex("addr","' + address + '")&page-size=15').pipe(
       map((res: Response) => { 
         return res['objects'] ; 
        }
      )) ;
       
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

   deleteEndpoint(address) {
     return new Observable<any>() ;
   }

   login(username,password) {
     return this.http.post(this.baseUrl + '/user/login', {username:username , password:password},{withCredentials:true}) ;
   }

   logout() {
     return this.http.post(this.baseUrl + '/user/logout',{}) ;
   }

   getAppVersion() {
     return this.http.get(this.baseUrl + '/app-status/version') ;
   }

   getSortsArrayAsString(sorts) {
    let sortsStr='' ;
    for(let sort of sorts) {
      sortsStr+=sort.prop + '|' + sort.dir + ',' ;
    }
    sortsStr = sortsStr.slice(0,sortsStr.length-1) ;
    return sortsStr ;
   }

   startStopFabric(action,fabric,rsn) {
     return this.http.post(this.baseUrl + '/uni/fb-' + fabric + '/' + action,{reason:rsn}) ;

   }

  verifyFabric(fabric) {
    return this.http.get(this.baseUrl + '/uni/fb-'+fabric+'/verify') ;
  }

  deleteFabric(fabric) {
    return this.http.delete(this.baseUrl + '/uni/fb-' + fabric) ;
  }

  updateFabric(fabric) {
    return this.http.patch(this.baseUrl + '/uni/fb-' + fabric.fabric,fabric) ;
  }

  createFabric(fabric) {
    return this.http.post(this.baseUrl + '/fabric' , fabric ) ;
  }

  getFabricSettings(fabric,settings) {
    return this.http.get(this.baseUrl + '/uni/fb-' + fabric + '/settings-' + settings) ;
  }

  getAllFabricSettings() {
    return this.http.get(this.baseUrl + '/ept/settings') ;
  }

  getFabric(fabric) {
    return this.http.get(this.baseUrl + '/uni/fb-' + fabric) ;
  }

  updateFabricSettings(fabricSettings:FabricSettings) {
    const fabric = fabricSettings.fabric ;
    return this.http.patch(this.baseUrl +'/uni/fb-' + fabric+ '/settings-default',fabricSettings) ;
  }

  createUser(user: User): Observable<any> {
    let toSave = new User(
      user.username,
      user.role,
      user.password
    );
    delete toSave.last_login;
    delete toSave.is_new;
    delete toSave.password_confirm;
    return this.http.post(this.baseUrl + '/user', toSave);
  }

  updateUser(user: User): Observable<any> {
    let toSave = new User(
      user.username,
      user.role,
      user.password
    );
    delete toSave.is_new;
    delete toSave.password_confirm;
    delete toSave.last_login;
    if (toSave.password == '') {
      delete toSave.password;
    }
    return this.http.patch(this.baseUrl + '/user/' + toSave.username, toSave);
  }

  deleteUser(user: User): Observable<any> {
    return this.http.delete(this.baseUrl + '/user/' + user.username);
  }

  getUsers(): Observable<UserList> {
    const options = {
      params: new HttpParams().set('sort', 'username|asc')
    };
    return this.http.get<UserList>(this.baseUrl + '/user', options);
  }

  getUserDetails(username: string) {
    const url = this.baseUrl + '/uni/username-' + username;
    return this.http.get(url);
  }





}
