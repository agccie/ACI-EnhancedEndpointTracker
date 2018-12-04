import {Component, OnDestroy, OnInit} from '@angular/core';
import {NavigationEnd, Router} from '@angular/router';
import {BackendService} from './_service/backend.service';
import {PreferencesService} from './_service/preferences.service';
import {environment} from '../environments/environment.app';
import {filter} from "rxjs/operators";

@Component({
    selector: 'app-root',
    templateUrl: './app.component.html',
})

export class AppComponent implements OnInit, OnDestroy {
    ls = localStorage;
    app_mode = environment.app_mode;
    konami: boolean;
    login_required: boolean;
    private stopListening: () => void;

    constructor(private router: Router, private backendService: BackendService, public prefs: PreferencesService) {
    }

    ngOnInit() {
        this.login_required = localStorage.getItem('isLoggedIn') != 'true';
        this.router.events.pipe(filter(event => event instanceof NavigationEnd)).subscribe(event => {
            this.login_required = localStorage.getItem('isLoggedIn') != 'true';
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

}
