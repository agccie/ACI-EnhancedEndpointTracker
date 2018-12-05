import {Injectable} from '@angular/core';
import {HttpClient, HttpParams} from '@angular/common/http';
import {Observable} from 'rxjs';
import {map} from 'rxjs/operators';
import {environment} from '../../environments/environment';
import {FabricSettings} from '../_model/fabric-settings';
import {User, UserList} from '../_model/user';
import {Fabric, FabricList} from "../_model/fabric";
import {EndpointList} from "../_model/endpoint";
import {QueueList} from "../_model/queue";


@Injectable({
    providedIn: 'root'
})

export class BackendService {
    baseUrl: any;
    domain: any;

    constructor(private http: HttpClient) {
        this.baseUrl = environment.api_entry;
    }

    getAppStatus() {
        return this.http.get(this.baseUrl + '/app-status');
    }

    getAppManagerStatus() {
        return this.http.get(this.baseUrl + '/app-status/manager', {withCredentials: true});
    }

    getFabrics(sorts = []): Observable<FabricList> {
        if (sorts.length == 0) {
            return this.http.get<FabricList>(this.baseUrl + '/fabric');
        } else {
            const sortsStr = this.getSortsArrayAsString(sorts);
            return this.http.get<FabricList>(this.baseUrl + '/fabric?sort=' + sortsStr);
        }
    }

    getActiveMacAndIps(fabric: Fabric, addressType) {
        const filterString = 'and(eq("fabric","' + fabric.fabric + '"),eq("type","' + addressType + '"),neq("events.0.status","deleted"))';
        return this.http.get(this.baseUrl + '/ept/endpoint?filter=' + filterString + '&count=1');
    }

    getFabricsOverviewTabData(fabricName, pageOffset, sorts, tab = 'endpoint'): Observable<EndpointList> {
        if (sorts.length === 0) {
            return this.http.get<EndpointList>(this.baseUrl + '/ept/' + tab + '?filter=eq("fabric","' + fabricName + '")&sort=fabric&page-size=25&page=' + pageOffset);
        } else {
            const sortsStr = this.getSortsArrayAsString(sorts);
            return this.http.get<EndpointList>(this.baseUrl + '/ept/' + tab + '?filter=eq("fabric","' + fabricName + '")&sort=' + sortsStr + '&page-size=25&page=' + pageOffset);
        }
    }

    getEndpoints(fabricName, pageOffset, sorts): Observable<EndpointList> {
        if (sorts.length === 0) {
            return this.http.get<EndpointList>(this.baseUrl + '/ept/endpoint?filter=eq("fabric","' + fabricName + '")&sort=fabric&page-size=25&page=' + pageOffset);
        } else {
            const sortsStr = this.getSortsArrayAsString(sorts);
            return this.http.get<EndpointList>(this.baseUrl + '/ept/endpoint?filter=eq("fabric","' + fabricName + '")&sort=' + sortsStr + '&page-size=25&page=' + pageOffset);
        }
    }

    getFilteredEndpoints(fabricName, sorts = [], offsubnetFilter = false, staleFilter = false, activeFilter = false, rapidFilter = false, tab = 'endpoint', pageOffset = 0, pageSize = 25): Observable<EndpointList> {
        let conditions = '';
        let fabricFilter = 'eq("fabric","' + fabricName + '")';
        let count = 0;
        let sortsStr = '';
        if (offsubnetFilter) {
            conditions += ',eq("is_offsubnet",' + offsubnetFilter + ')';
            count++;
        }
        if (staleFilter) {
            conditions += ',eq("is_stale",' + staleFilter + ')';
            count++;
        }
        if (activeFilter) {
            conditions += ',or(eq("events.0.status","created"),eq("events.0.status","modified"))';
            count++;
        }
        if (rapidFilter) {
            conditions += ',eq("is_rapid",' + rapidFilter + ')';
            count++;
        }
        if (count > 1) {
            conditions = conditions.replace(',', '');
            conditions = 'and(' + fabricFilter + ',or(' + conditions + '))';
        } else if (count === 1) {
            conditions = 'and(' + fabricFilter + conditions + ')';
        } else {
            conditions = fabricFilter
        }
        if (sorts.length > 0) {
            sortsStr = '&sort=' + this.getSortsArrayAsString(sorts);

        }
        let url = this.baseUrl + '/ept/' + tab + '?page-size=' + pageSize + '&page=' + pageOffset + '&filter=' + conditions + sortsStr;
        return this.http.get<EndpointList>(url);
    }

    getEndpoint(fabricName, vnid, address): Observable<EndpointList> {
        return this.http.get<EndpointList>(this.baseUrl + '/uni/fb-' + fabricName + '/endpoint/vnid-' + vnid + '/addr-' + address);
    }

    getMoveEventsForEndpoint(fabricName: string, vnid, address) {
        return this.http.get(this.baseUrl + `/ept/move?filter=and(eq("fabric","${fabricName}"),eq("vnid",${vnid}),eq("addr","${address}"))`);
    }

    getNodesForOffsubnetEndpoints(fabricName: string, vnid, address, tab): Observable<EndpointList> {
        return this.http.get<EndpointList>(this.baseUrl + '/ept/' + tab + '?filter=and(eq("fabric","' + fabricName + '"),eq("vnid",' + vnid + '),eq("addr","' + address + '"))&include=node');
    }

    getEndpointHistoryPerNode(fabricName: string, node, vnid, address): Observable<EndpointList> {
        return this.http.get<EndpointList>(this.baseUrl + '/uni/fb-' + fabricName + '/history/node-' + node + '/vnid-' + vnid + '/addr-' + address);
    }

    deleteEndpoint(fabricName: String, vnid, address) {
        return this.http.delete(this.baseUrl + '/uni/fb-' + fabricName + '/endpoint/vnid-' + vnid + '/addr-' + address + '/delete');
    }

    login(username, password) {
        return this.http.post(this.baseUrl + '/user/login', {
            username: username,
            password: password
        }, {withCredentials: true});
    }

    logout() {
        return this.http.post(this.baseUrl + '/user/logout', {});
    }

    getSearchResults(address) {
        return this.http.get(this.baseUrl + '/ept/endpoint?filter=regex("addr","' + address + '")&page-size=15').pipe(
            map((res: Response) => {
                return res['objects'];
            })
        );
    }

    getAppVersion() {
        return this.http.get(this.baseUrl + '/app-status/version');
    }

    getSortsArrayAsString(sorts) {
        let sortsStr = '';
        for (let sort of sorts) {
            sortsStr += sort.prop + '|' + sort.dir + ',';
        }
        sortsStr = sortsStr.slice(0, sortsStr.length - 1);
        return sortsStr;
    }

    startFabric(fabric: Fabric, reason = '') {
        return this.http.post(this.baseUrl + '/uni/fb-' + fabric.fabric + '/start', {reason: reason});
    }

    stopFabric(fabric: Fabric, reason = '') {
        return this.http.post(this.baseUrl + '/uni/fb-' + fabric.fabric + '/stop', {reason: reason});
    }

    verifyFabric(fabric: Fabric) {
        return this.http.get(this.baseUrl + '/uni/fb-' + fabric.fabric + '/verify');
    }

    deleteFabric(fabric: Fabric) {
        return this.http.delete(this.baseUrl + '/uni/fb-' + fabric.fabric);
    }

    updateFabric(fabric: Fabric) {
        return this.http.patch(this.baseUrl + '/uni/fb-' + fabric.fabric, fabric);
    }

    createFabric(fabric: Fabric) {
        let toSave = new Fabric(
            fabric.fabric,
            fabric.apic_hostname,
            fabric.apic_username,
            fabric.apic_password,
            fabric.apic_cert,
            fabric.ssh_username,
            fabric.ssh_password,
            fabric.max_events,
        );
        delete toSave.status;
        delete toSave.mac;
        delete toSave.ipv4;
        delete toSave.ipv6;
        return this.http.post(this.baseUrl + '/fabric', toSave);
    }

    getFabricSettings(fabricName: string, settings) {
        return this.http.get(this.baseUrl + '/uni/fb-' + fabricName + '/settings-' + settings);
    }

    getFabricByName(fabricName: string): Observable<FabricList> {
        return this.http.get<FabricList>(this.baseUrl + '/uni/fb-' + fabricName);
    }

    updateFabricSettings(fabricSettings: FabricSettings) {
        const fabric = fabricSettings.fabric;
        return this.http.patch(this.baseUrl + '/uni/fb-' + fabric + '/settings-default', fabricSettings);
    }

    getFabricStatus(fabric: Fabric) {
        return this.http.get(this.baseUrl + '/uni/fb-' + fabric.fabric + '/status');
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

    getQueues(pageOffset: number, sorts): Observable<QueueList> {
        if (sorts.length === 0) {
            return this.http.get<QueueList>(this.baseUrl + '/ept/queue?include=dn,proc,queue,start_timestamp,total_rx_msg,total_tx_msg&page-size=10&page=' + pageOffset);
        } else {
            const sortsStr = this.getSortsArrayAsString(sorts);
            return this.http.get<QueueList>(this.baseUrl + '/ept/queue?include=dn,proc,queue,start_timestamp,total_rx_msg,total_tx_msg&sort=' + sortsStr + '&page-size=10&page=' + pageOffset);
        }
    }

    getQueue(dn: string): Observable<QueueList> {
        return this.http.get<QueueList>(this.baseUrl + dn);
    }

    getPerNodeHistory(fabric, node, vnid, address) {
        return this.http.get(this.baseUrl + '/uni/fb-' + fabric + '/history/node-' + node + '/vnid-' + vnid + '/addr-' + address);
    }

    offsubnetStaleEndpointHistory(fabric, vnid, address, endpointState, table) {

        return this.http.get(this.baseUrl + '/ept/' + table + '?filter=and(eq("' + endpointState + '",true),eq("fabric","' + fabric + '"),eq("vnid",' + vnid + '),eq("addr","' + address + '"))');
    }

    testEmailNotifications(type: String, fabricName: String) {
        return this.http.post(this.baseUrl + '/uni/fb-' + fabricName + '/settings-default/test/' + type, {});
    }

    dataplaneRefresh(fabricName: String, vnid: String, address: String) {
        return this.http.post(this.baseUrl + '/uni/fb-' + fabricName + '/endpoint/vnid-' + vnid + '/addr-' + address + '/refresh', {});
    }

    getRapidEndpoints(fabricName: String, vnid: String, address: String): Observable<EndpointList> {
        return this.http.get<EndpointList>(this.baseUrl + `/ept/rapid?filter=and(eq("fabric","${fabricName}"),eq("vnid",${vnid}),eq("addr","${address}"))`)
    }

    getClearedEndpoints(fabricName: String, vnid: String, address: String): Observable<EndpointList> {
        return this.http.get<EndpointList>(this.baseUrl + `/ept/remediate?filter=and(eq("fabric","${fabricName}"),eq("vnid",${vnid}),eq("addr","${address}"))`)
    }

    getAllOffsubnetStaleEndpoints(fabric:String,vnid:String,address:String,table:String):Observable<EndpointList> {
        return this.http.get<EndpointList>(this.baseUrl + `/ept/${table}?filter=and(eq("fabric","${fabric}"),eq("vnid",${vnid}),eq("addr","${address}"))`) ;
    }

    clearNodes(fabric:String,vnid:String,addr:String,nodeList:Array<Number>) {
        return this.http.post(this.baseUrl + `/uni/fb-${fabric}/endpoint/vnid-${vnid}/addr-${addr}/clear`,nodeList)
    }


}
