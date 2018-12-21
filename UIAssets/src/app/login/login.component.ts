import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {Router} from '@angular/router';
import {BackendService} from '../_service/backend.service';
import {environment} from "../../environments/environment";
import {ModalService} from '../_service/modal.service';
import {PreferencesService} from "../_service/preferences.service";
import {UserList} from '../_model/user';

@Component({
    selector: 'app-login',
    templateUrl: './login.component.html'
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

    constructor(private router: Router, private backendService: BackendService, private pref: PreferencesService,
                public modalService: ModalService) {
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
                localStorage.setItem('isLoggedIn', 'true');
                localStorage.setItem('userName', this.username);
                this.pref.userName = this.username;
                this.backendService.getUserDetails(this.username).subscribe(
                    (data) => {
                        let user_list = new UserList(data);
                        if(user_list.objects.length>0){
                            localStorage.setItem('userRole', ""+user_list.objects[0].role);
                            this.pref.userRole = user_list.objects[0].role;
                        }
                        this.router.navigate(['/']);
                    }, (error) => {
                        this.router.navigate(['/']);
                    }
                );
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
