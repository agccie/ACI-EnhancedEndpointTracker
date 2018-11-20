import {Component, OnInit} from '@angular/core';
import {Router} from '@angular/router';
import {BackendService} from './_service/backend.service';
import {PreferencesService} from './_service/preferences.service';
import {environment} from '../environments/environment.app';

@Component({
    selector: 'app-root',
    templateUrl: './app.component.html',
    styleUrls: ['./app.component.css']
})

export class AppComponent implements OnInit {
    menu: any;
    cul: number;
    ls = localStorage;
    app_mode = environment.app_mode;

    constructor(private router: Router, private bs: BackendService, public prefs: PreferencesService) {
        this.menu = [
            {name: 'Fabrics', icon: 'icon-computer', active: true, link: 'fabrics/fabric-overview'},
            {name: 'Users', icon: 'icon-user', active: false, link: 'users'},
            {name: 'Settings', icon: 'icon-cog', active: false, link: 'settings'},
        ];
        this.cul = this.prefs.cul;
    }

    ngOnInit() {

    }

    logout() {
        this.bs.logout().subscribe(
            (data) => {
                console.log(data);
                localStorage.setItem('cul', '0');
                this.prefs.cul = 0;
                this.router.navigate(['/']);
            },
            (error) => {
                this.prefs.cul = 0;
                this.router.navigate(['/']);
            }
        )
    }

}
