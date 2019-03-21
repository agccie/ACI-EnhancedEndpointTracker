import {Component, OnDestroy, OnInit, TemplateRef, ViewChild, Renderer2} from '@angular/core';
import {ActivatedRoute, NavigationEnd, Router} from '@angular/router';
import {BackendService} from './_service/backend.service';
import {CookieService} from 'ngx-cookie-service';
import {PreferencesService} from './_service/preferences.service';
import {environment} from '../environments/environment';
import {ModalService} from './_service/modal.service';
import {Version} from './_model/version';
import {FabricList} from './_model/fabric';
import {filter, map, tap, repeatWhen, retryWhen, delay, takeWhile} from "rxjs/operators";


@Component({
    selector: 'app-root',
    templateUrl: './app.component.html'
})

export class AppComponent implements OnInit, OnDestroy {
    ls = localStorage;
    app_mode: boolean = false;
    login_required: boolean = false;
    fabricName: string = '';
    endpointExpanded: boolean = false;
    sidebarCollapsed: boolean = false;
    loadingAbout: boolean = false;
    appLoading: boolean = true;
    appFabricDiscoveryLoading: boolean = true;
    discoveredFabric: string = "";
    appLoadingStatus: string = "";
    appCookieAcquired: boolean = false;
    @ViewChild('aboutModal') aboutModal: TemplateRef<any>;
    @ViewChild('generalModal') generalModal: TemplateRef<any>;
    version: Version = new Version();
    feedbackUrl: string = "";
    private stopListening: () => void;

    constructor(private router: Router, private backendService: BackendService, public prefs: PreferencesService,
                private cookieService: CookieService, private renderer: Renderer2,
                private activatedRoute: ActivatedRoute, public modalService: ModalService) {
        this.endpointExpanded = false;
        this.sidebarCollapsed = true;
        this.app_mode = environment.app_mode;
        this.stopListening = renderer.listen('window', 'message', this.handleMessage.bind(this));
    }

    ngOnInit() {
        if(this.app_mode){
            this.appLoadingStatus = "Waiting for tokens"
        } else {
            this.appLoadingStatus = 'Waiting for backend application';
            this.waitForAppReady();
        }
        this.login_required = localStorage.getItem('isLoggedIn') != 'true';
        this.router.events.pipe(filter(event => event instanceof NavigationEnd)).subscribe(event => {
            this.login_required = localStorage.getItem('isLoggedIn') != 'true';
            this.activatedRoute.firstChild.paramMap.subscribe(params => {
                this.fabricName = params.get('fabric');
            });
        });
        this.modalService.generalModal = this.generalModal;
    }

    ngOnDestroy() {
        this.stopListening();
        if (!this.app_mode) {
            localStorage.removeItem('isLoggedIn');
            localStorage.removeItem('token');
            localStorage.removeItem('session');
            this.backendService.logout().subscribe(() => {});
        }
    }

    logout() {
        this.backendService.logout().subscribe(
            (data) => {
                this.modalService.hideModal();
                localStorage.removeItem('isLoggedIn');
                this.router.navigate(['login']);
            }, 
            (error) => {
                localStorage.removeItem('isLoggedIn');
                this.modalService.setModalError({
                    "subtitle": "failed to logout."
                });
            }
        )
    }

    getVersionInfo() {
        this.loadingAbout = true;
        this.backendService.getAppVersion().subscribe(
            (data) => {
                this.loadingAbout = false;
                this.version.sync(data);
                // set feedbackUrl if contact_email is set
                if(this.version.contact_email.length>0){
                    this.feedbackUrl = "mailto:"+this.version.contact_email+"?Subject=Feedback for "+this.version.app_id+" app";
                }
            }, 
            (error) => {
                this.loadingAbout = false;
            }
        );
    }

    showAbout() {
        this.modalService.openModal(this.aboutModal);
        this.getVersionInfo();
    }

    onSidebarClicked($event: MouseEvent) {
        this.sidebarCollapsed = !this.sidebarCollapsed;
    }

    onContentClicked($event: MouseEvent) {
        this.endpointExpanded = false;
    }

    onEndpointExpand($event: MouseEvent) {
        this.endpointExpanded = !this.endpointExpanded;
        $event.stopPropagation();
    }

    handleMessage(event: Event) {
        const message = event as MessageEvent;
        if (environment.app_mode) {
          const data = JSON.parse(message.data);
          if (data.hasOwnProperty('token') && data.hasOwnProperty('urlToken')) {
            this.cookieService.set('app_' + environment.aci_vendor + '_' + environment.aci_appId + '_token', data['token']);
            this.cookieService.set('app_' + environment.aci_vendor + '_' + environment.aci_appId + '_urlToken', data['urlToken']);
            if (!this.appCookieAcquired) {
              this.appCookieAcquired = true;
              this.appLoadingStatus = 'Waiting for backend application';
              this.waitForAppReady();
            }
          }
        }
    }
    
    waitForAppReady() {
        //app-status API will return 200 ok when ready else will return an error (503 or 500) with error string
        //if not yet ready. This needs to wait for 200 ok else update message displayed to the user.
        this.backendService.getAppStatus().pipe(
            map((data) => data),
            retryWhen( err => err.pipe(
                tap(val => {
                    console.log(val);
                    let status = "";
                    let msg = "";
                    try{
                        if("status" in val){
                            status = "("+val["status"]+")";
                        }
                        if("error" in val && "error" in val["error"]){
                            msg = status+" "+val["error"]["error"];
                        } else if("error" in val && "message" in val["error"]){
                            msg = status+" "+val["error"]["message"];
                        } else {
                            msg = status+" Waiting for backend application";
                        }
                    } catch(err){msg = "Waiting for backend application";}
                    this.appLoadingStatus = msg;
                }),
                delay(1000)
            ))
        ).subscribe(
            (data)=>{
                this.appLoadingStatus = "App loading complete."
                this.getVersionInfo();
                if(this.app_mode){
                    this.waitForFabricDiscovery();
                } else {
                    this.appLoading = false;
                }
            }
        )
    }

    // in app mode we need to wait until fabric is discovered.
    waitForFabricDiscovery(){
        this.appLoadingStatus = "Waiting for fabric discovery to complete."
        this.appFabricDiscoveryLoading = true;
        this.backendService.getFabricsBrief().pipe(
            repeatWhen(delay(1000)),
            takeWhile(()=> this.appFabricDiscoveryLoading)
        ).subscribe(
            (data) => {
                let fabric_list = new FabricList(data);
                if(fabric_list.objects.length>0){
                    this.discoveredFabric = fabric_list.objects[0].fabric;
                    this.appLoadingStatus = "Discovered fabric "+this.discoveredFabric;
                    this.appFabricDiscoveryLoading = false;
                    if(this.app_mode){
                        this.waitForManagerReady();
                    } else {
                        this.appLoading = false;
                        this.router.navigate(['/fabric', this.discoveredFabric]);
                    }
                }
            },
            (error)=>{
                console.log(error);
                this.appLoadingStatus = "failed to load fabric status."
                if("error" in error && "error" in error["error"]){
                    this.appLoadingStatus+= " "+error["error"]["error"];
                }
            }
        )
    }

    // in app mode, need to also wait until manager process is ready OR until maximum wait time 
    waitForManagerReady(){
        let managerCheckCount = 300;
        this.appLoadingStatus = "Waiting for manager process."
        this.backendService.getAppManagerStatus().pipe(
            repeatWhen(delay(1000)),
            takeWhile(()=> this.appLoading)
        ).subscribe(
            (data) => {
                managerCheckCount--;
                if("manager" in data && "status" in data["manager"] && data["manager"]["status"] == "running"){
                    this.appLoadingStatus = "Manager process is ready"
                    this.appLoading = false;
                    this.router.navigate(['/fabric', this.discoveredFabric]);
                } else {
                    console.log("manager not ready");
                    console.log(data);
                    if(managerCheckCount<=0){
                        console.log("maximum manager check count exceeded, proceeding anyways.")
                        this.appLoading = false;
                        this.router.navigate(['/fabric', this.discoveredFabric]);
                    }
                }
            },
            (error)=>{
                console.log(error);
                this.appLoadingStatus = "failed to load manager status."
                if("error" in error && "error" in error["error"]){
                    this.appLoadingStatus+= " "+error["error"]["error"];
                }
            }
        )
    }

}
