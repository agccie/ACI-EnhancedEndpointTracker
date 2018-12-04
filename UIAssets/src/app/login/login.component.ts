import {Component, OnInit, ViewChild, TemplateRef} from '@angular/core';
import {Router} from '@angular/router';
import {BackendService} from '../_service/backend.service';
import {PreferencesService} from '../_service/preferences.service';
import {environment} from "../../environments/environment";
import { ModalService } from '../_service/modal.service';

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
    @ViewChild('errorMsg') msgModal : TemplateRef<any> ;
    constructor(private router: Router, private bs: BackendService, private prefs: PreferencesService, public modalService:ModalService) {
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
                    const msg = 'Failed to fetch app version! ' + error['error']['error'] ;
                    this.modalService.setAndOpenModal('error','Error',msg,this.msgModal) ; 
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
                const msg = 'Failed to login! ' + error['error']['error'] ;
                    this.modalService.setAndOpenModal('error','Error',msg,this.msgModal) ; 
            }
        )
    }
}
