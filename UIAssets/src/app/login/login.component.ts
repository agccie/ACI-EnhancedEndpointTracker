import {Component, OnInit} from '@angular/core';
import {Router} from '@angular/router';
import {BackendService} from '../_service/backend.service';
import {PreferencesService} from '../_service/preferences.service';
import {environment} from "../../environments/environment";

@Component({
    selector: 'app-login',
    templateUrl: './login.component.html',
    styleUrls: ['./login.component.css']
})
export class LoginComponent implements OnInit {
    title: string;
    username = '';
    password = '';
    showModal = false;
    modalTitle = '';
    modalBody = '';
    version = 'Not Available';
    loading = false;
    ls: Storage;

    constructor(private router: Router, private bs: BackendService, private prefs: PreferencesService) {
        this.title = 'Endpoint Tracker';
        this.ls = localStorage;
        if (environment.app_mode) {
            localStorage.setItem('isLoggedIn', 'true');
            this.router.navigate(['/']);
        }
    }

    ngOnInit() {
        if (localStorage.getItem('isLoggedIn') === 'true') {
            this.router.navigate(['/']);
        } else {
            this.bs.getAppVersion().subscribe(
                (data) => {
                    this.version = data['version'];
                },
                (error) => {
                    this.modalTitle = 'Version Error';
                    this.modalBody = error['error'];
                    this.showModal = true;
                }
            )
        }
    }

    onSubmit() {
        this.bs.login(this.username, this.password).subscribe(
            (data) => {
                if (data['success'] === true) {
                    localStorage.setItem('isLoggedIn', 'true');
                    localStorage.setItem('userName', this.username);
                    this.bs.getUserDetails(this.username).subscribe((response) => {
                        const userDetails = response['objects'][0]['user'];
                        localStorage.setItem('userRole', userDetails['role']);
                    }, (error) => {
                    });
                    this.router.navigate(['/']);
                }
            },
            (error) => {
                this.modalTitle = 'Login Error';
                this.modalBody = error['error']['error'];
                this.showModal = true;
            }
        )
    }
}
