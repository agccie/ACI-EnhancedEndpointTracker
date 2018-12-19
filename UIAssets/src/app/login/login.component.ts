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
    title: string = 'Endpoint Tracker';
    username = '';
    password = '';
    modalTitle = '';
    modalBody = '';
    version = '-';
    loading = false;
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(private router: Router, private backendService: BackendService, public modalService: ModalService) {
        if (environment.app_mode) {
            localStorage.setItem('isLoggedIn', 'true');
            this.router.navigate(['/']);
        }
    }

    ngOnInit() {
        if (localStorage.getItem('isLoggedIn') === 'true') {
            this.router.navigate(['/']);
        } else {
            this.loading = true;
            this.backendService.getAppVersion().subscribe(
                (data) => {
                    this.loading = false;
                    this.version = data['version'];
                },
                (error) => {
                    this.loading = false;
                }
            )
        }
    }

    onSubmit() {
        this.loading = true;
        this.backendService.login(this.username, this.password).subscribe(
            (data) => {
                if (data['success'] === true) {
                    localStorage.setItem('isLoggedIn', 'true');
                    localStorage.setItem('userName', this.username);
                    this.backendService.getUserDetails(this.username).subscribe((response) => {
                        const userDetails = response['objects'][0]['user'];
                        localStorage.setItem('userRole', userDetails['role']);
                        this.router.navigate(['/']);
                    }, (error) => {
                        this.router.navigate(['/']);
                    });
                } else {
                    this.loading = false;
                }
            },
            (error) => {
                this.loading = false;
                if("status" in error && error["status"]==401){
                    this.modalService.setModalInfo({
                        "title": "Login Failed",
                        "subtitle": 'User credentials incorrect'
                    });
                } else {
                    this.modalService.setModalError({
                        "body": 'Error during login. ' + error['error']['error']
                    }); 
                }
            }
        )
    }
}
