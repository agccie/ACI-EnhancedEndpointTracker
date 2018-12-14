import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {Router} from '@angular/router';
import {BackendService} from '../_service/backend.service';
import {environment} from "../../environments/environment";
import {ModalService} from '../_service/modal.service';

@Component({
    selector: 'app-login',
    templateUrl: './login.component.html',
    styleUrls: ['./login.component.css']
})

export class LoginComponent implements OnInit {
    title: string;
    username = '';
    password = '';
    modalTitle = '';
    modalBody = '';
    version = 'Not Available';
    loading = false;
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(private router: Router, private backendService: BackendService, public modalService: ModalService) {
        this.title = 'Endpoint Tracker';
        if (environment.app_mode) {
            localStorage.setItem('isLoggedIn', 'true');
            this.router.navigate(['/']);
        }
    }

    ngOnInit() {
        if (localStorage.getItem('isLoggedIn') === 'true') {
            this.router.navigate(['/']);
        } else {
            this.backendService.getAppVersion().subscribe(
                (data) => {
                    this.version = data['version'];
                },
                (error) => {
                    const msg = 'Failed to fetch app version! ' + error['error']['error'];
                    this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
                }
            )
        }
    }

    onSubmit() {
        this.backendService.login(this.username, this.password).subscribe(
            (data) => {
                if (data['success'] === true) {
                    localStorage.setItem('isLoggedIn', 'true');
                    localStorage.setItem('userName', this.username);
                    this.backendService.getUserDetails(this.username).subscribe((response) => {
                        const userDetails = response['objects'][0]['user'];
                        localStorage.setItem('userRole', userDetails['role']);
                    }, (error) => {
                    });
                    this.router.navigate(['/']);
                }
            },
            (error) => {
                const msg = 'Failed to login! ' + error['error']['error'];
                this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
            }
        )
    }
}
