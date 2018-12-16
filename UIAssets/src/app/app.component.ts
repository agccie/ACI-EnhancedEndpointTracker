import {Component, OnDestroy, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {ActivatedRoute, NavigationEnd, Router} from '@angular/router';
import {BackendService} from './_service/backend.service';
import {PreferencesService} from './_service/preferences.service';
import {environment} from '../environments/environment';
import {filter} from "rxjs/operators";
import {ModalService} from './_service/modal.service';
import {Version} from './_model/version';

@Component({
    selector: 'app-root',
    templateUrl: './app.component.html',
})

export class AppComponent implements OnInit, OnDestroy {
    ls = localStorage;
    app_mode: boolean;
    konami: boolean;
    login_required: boolean;
    menuVisible: boolean;
    fabricName: string;
    endpointExpanded: boolean;
    configurationExpanded: boolean;
    sidebarCollapsed: boolean;
    @ViewChild('abouttemplate') msgModal: TemplateRef<any>;
    authors = ['Andy Gossett', 'Axel Bodart', 'Hrishikesh Deshpande'];
    version: Version;
    private stopListening: () => void;

    constructor(private router: Router, private backendService: BackendService, public prefs: PreferencesService,
                private activatedRoute: ActivatedRoute, public modalService: ModalService) {
        this.endpointExpanded = false;
        this.configurationExpanded = false;
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
        localStorage.removeItem('isLoggedIn');
        this.backendService.logout().subscribe(() => {
            this.router.navigate(['login']);
        });
    }

    onKonami() {
        this.konami = true;
    }

    noKonami() {
        this.konami = false;
    }

    shuffleAuthor() {
        let j, x, i;
        for (i = this.authors.length - 1; i > 0; i--) {
            j = Math.floor(Math.random() * (i + 1));
            x = this.authors[i];
            this.authors[i] = this.authors[j];
            this.authors[j] = x;
        }
    }

    getVersion() {
        this.backendService.getVersion().subscribe(
            (results) => {
                this.version = results;
                this.shuffleAuthor();
                this.modalService.openModal(this.msgModal);
            }
        );
    }
}
