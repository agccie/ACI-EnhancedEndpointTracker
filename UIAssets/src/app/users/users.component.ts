import {Component, OnInit, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../_service/backend.service';
import {PreferencesService} from '../_service/preferences.service';
import {User, UserList, UserRoles} from '../_model/user';
import {ModalService} from '../_service/modal.service';

@Component({
    selector: 'app-users',
    templateUrl: './users.component.html',
    styleUrls: ['./users.component.css']
})
export class UsersComponent implements OnInit {
    rows;
    allUserRoles: any[];
    loading: boolean;
    users: User[];
    updateUser: User;
    usernameSort: any;
    userRole: number;
    userName: string;
    pageSize: number;
    @ViewChild('updateUserTemplate') updateUserModal: TemplateRef<any>;

    constructor(private backendService: BackendService, private prefs: PreferencesService, private modalService: ModalService) {
        this.userName = this.prefs.userName;
        this.userRole = this.prefs.userRole;
        this.pageSize = this.prefs.pageSize;
        this.allUserRoles = UserRoles;
    }

    ngOnInit(): void {
        this.getUsers();
    }

    getUsers() {
        this.loading = true;
        this.backendService.getUsers().subscribe(
            (data) => {
                let user_list = new UserList(data);
                this.rows = user_list.objects;
                this.users = user_list.objects;
                this.loading = false;
            }, 
            (error) => {
                this.loading = false;
                this.modalService.setModalError({
                    "body": 'Failed to get users. '+ error['error']['error']
                });
            }
        );
    }

    updateFilter(event) {
        const val = event.target.value.toLowerCase();
        this.rows = this.users.filter(function (d) {
            return d.username.toLowerCase().indexOf(val) !== -1 || !val;
        });
    }

    onAddUser(){
        this.updateUser = new User();
        this.updateUser.is_new = true;
        this.modalService.openModal(this.updateUserModal);
    }

    onUpdateUser(user:User){
        //for some reason on modal tear down it destroys the update user, let's clone it
        this.updateUser = user.clone();
        this.updateUser.is_new = false;
        this.modalService.openModal(this.updateUserModal);
    }

    onDeleteUser(user:User){
        let that = this;
        this.updateUser = user.clone();
        this.modalService.setModalConfirm({
            "modalType": "info",
            "title": "Wait",
            "subtitle": "Are you sure you want to delete "+this.updateUser.username+"?",
            "callback": function(){
                that.loading = true;
                that.modalService.setModalInfo({
                    "title": "Wait",
                    "subtitle": "Are you sure you want to delete "+that.updateUser.username+"?",
                    "loading": that.loading,
                });
                that.backendService.deleteUser(that.updateUser).subscribe(
                    (data) => {
                        that.modalService.hideModal();
                        that.loading = false;
                        that.getUsers();
                    }, 
                    (error) => {
                        that.modalService.hideModal();
                        that.loading = false;
                        that.modalService.setModalError({
                            "body": 'Failed to delete user. '+ error['error']['error']
                        });
                    }
                );
            }
        });
    }

    public onSubmit() {
        this.loading = true;
        if (this.updateUser.is_new) {
            this.backendService.createUser(this.updateUser).subscribe(
                (data) => {
                    this.modalService.hideModal();
                    this.loading = false;
                    this.getUsers();
                }, (error) => {
                    this.modalService.hideModal();
                    this.loading = false;
                    this.modalService.setModalError({
                        "body": 'Failed create user. '+ error['error']['error']
                    });
                }
            );
        } else {
            this.backendService.updateUser(this.updateUser).subscribe(
                (data) => {
                    this.modalService.hideModal();
                    this.loading = false;
                    this.getUsers();
                }, (error) => {
                    this.modalService.hideModal();
                    this.loading = false;
                    this.modalService.setModalError({
                        "body": 'Failed create user. '+ error['error']['error']
                    });
                }
            );
        }
    }
}
