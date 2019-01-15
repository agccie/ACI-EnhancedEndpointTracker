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
    appLoadingStatus: string = "";
    appCookieAcquired: boolean = false;
    @ViewChild('aboutModal') aboutModal: TemplateRef<any>;
    @ViewChild('generalModal') generalModal: TemplateRef<any>;
    version: Version;
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

    showAbout() {
        this.loadingAbout = true;
        this.modalService.openModal(this.aboutModal);
        this.backendService.getVersion().subscribe(
            (data) => {
                this.loadingAbout = false;
                this.version = data;
            }, 
            (error) => {
                this.loadingAbout = false;
            }
        );
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
                    this.appLoadingStatus = msg;
                }),
                delay(1000)
            ))
        ).subscribe(
            (data)=>{
                this.appLoadingStatus = "App loading complete."
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
        this.backendService.getFabricsBrief().pipe(
            repeatWhen(delay(1000)),
            takeWhile(()=> this.appLoading)
        ).subscribe(
            (data) => {
                let fabric_list = new FabricList(data);
                if(fabric_list.objects.length>0){
                    let fabric = fabric_list.objects[0].fabric;
                    this.appLoadingStatus = "Discovered fabric "+fabric;
                    this.appLoading = false;
                    this.router.navigate(['/fabric', fabric]);
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
}
