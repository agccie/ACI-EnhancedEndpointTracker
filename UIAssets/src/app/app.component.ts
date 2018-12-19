import {Component, OnDestroy, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {ActivatedRoute, NavigationEnd, Router} from '@angular/router';
import {BackendService} from './_service/backend.service';
import {PreferencesService} from './_service/preferences.service';
import {environment} from '../environments/environment';
import {filter} from "rxjs/operators";
import {ModalService} from './_service/modal.service';
import {Version} from './_model/version';
import { convertToR3QueryMetadata } from '@angular/core/src/render3/jit/directive';

@Component({
    selector: 'app-root',
    templateUrl: './app.component.html'
})

export class AppComponent implements OnInit, OnDestroy {
    ls = localStorage;
    app_mode: boolean;
    login_required: boolean;
    menuVisible: boolean;
    fabricName: string;
    endpointExpanded: boolean;
    sidebarCollapsed: boolean;
    @ViewChild('abouttemplate') aboutModal: TemplateRef<any>;
    @ViewChild('generalModal') generalModal: TemplateRef<any>;
    authors = ['Andy Gossett', 'Axel Bodart', 'Hrishikesh Deshpande'];
    version: Version;
    private stopListening: () => void;

    constructor(private router: Router, private backendService: BackendService, public prefs: PreferencesService,
                private activatedRoute: ActivatedRoute, public modalService: ModalService) {
        this.endpointExpanded = false;
        this.sidebarCollapsed = true;
        this.app_mode = environment.app_mode;
    }

    ngOnInit() {
        localStorage.setItem('menuVisible', 'false');
        this.login_required = localStorage.getItem('isLoggedIn') != 'true';
        this.router.events.pipe(filter(event => event instanceof NavigationEnd)).subscribe(event => {
            this.login_required = localStorage.getItem('isLoggedIn') != 'true';
            this.menuVisible = localStorage.getItem('menuVisible') == 'true';
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
            this.backendService.logout().subscribe(() => {
            });
        }
    }

    logout() {
        this.modalService.setModalInfo({
            "title": "Logging out",
            "loading": true,
        })
        localStorage.removeItem('isLoggedIn');
        this.backendService.logout().subscribe(
            (data) => {
                this.modalService.hideModal();
                this.router.navigate(['login']);
            }, 
            (error) => {
                this.modalService.setModalError({
                    "subtitle": "failed to logout."
                });
            }
        )
    }

    getVersion() {
        this.backendService.getVersion().subscribe(
            (results) => {
                this.version = results;
                this.modalService.openModal(this.aboutModal);
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
}
