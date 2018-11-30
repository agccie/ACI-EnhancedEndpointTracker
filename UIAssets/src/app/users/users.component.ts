import {Component, OnInit, TemplateRef} from '@angular/core';
import {BackendService} from '../_service/backend.service';
import {PreferencesService} from '../_service/preferences.service';
import {User, UserList} from '../_model/user';
import {BsModalRef, BsModalService} from 'ngx-bootstrap';

@Component({
    selector: 'app-users',
    templateUrl: './users.component.html',
    styleUrls: ['./users.component.css']
})
export class UsersComponent implements OnInit {
    rows;
    modalRef: BsModalRef;
    loading: boolean;
    loadingMessage: string;
    selectedUser: User;
    users: User[];
    user: User;
    usernameSort: any;
    userRole: number;
    userName: string;
    roles: ({ id: number; name: string })[];
    pageSize: number;

    constructor(private backendService: BackendService, private prefs: PreferencesService, private modalService: BsModalService) {
        this.loadingMessage = 'Loading users';
        this.roles = [
            {'id': 0, name: 'Admin'},
            {'id': 1, name: 'User'},
        ];
        this.userName = localStorage.getItem('userName');
        this.userRole = parseInt(localStorage.getItem('userRole'));
        this.pageSize = this.prefs.pageSize;
    }

    ngOnInit(): void {
        this.getUsers();
    }

    getUsers() {
        this.loading = true;
        this.backendService.getUsers().subscribe((results: UserList) => {
            const objects = results.objects;
            let tempRows = [];
            for (let obj of objects) {
                tempRows.push(obj['user'])
            }
            this.users = tempRows;
            this.rows = tempRows;
            this.loading = false;
        }, (err) => {
            this.loading = false;
        });
    }

    updateFilter(event) {
        const val = event.target.value.toLowerCase();
        this.rows = this.users.filter(function (d) {
            return d.username.toLowerCase().indexOf(val) !== -1 || !val;
        });
    }

    deleteUser() {
        this.modalRef.hide();
        this.loading = true;
        this.backendService.deleteUser(this.selectedUser).subscribe((results) => {
            this.getUsers();
        }, (err) => {
            this.loading = false;
        });
    }

    public onSubmit() {
        this.modalRef.hide();
        this.loading = true;
        if (this.user.is_new) {
            this.backendService.createUser(this.user).subscribe((results) => {
                this.getUsers();
            }, (err) => {
                this.loading = false;
            });
        } else {
            this.backendService.updateUser(this.user).subscribe((results) => {
                this.getUsers();
            }, (err) => {
                this.loading = false;
            });
        }
    }

    public openAddModal(template: TemplateRef<any>) {
        this.user = new User();
        this.modalRef = this.modalService.show(template, {
            animated: true,
            keyboard: true,
            backdrop: true,
            ignoreBackdropClick: false,
            class: 'modal-lg',
        });
    }

    public openModal(template: TemplateRef<any>, user: User) {
        this.selectedUser = user;
        this.user = new User(
            user.username,
            user.role,
            user.password,
            user.last_login,
            false
        );
        this.modalRef = this.modalService.show(template, {
            animated: true,
            keyboard: true,
            backdrop: true,
            ignoreBackdropClick: false,
            class: 'modal-lg',
        });
    }

    public hideModal() {
        this.modalRef.hide();
    }

}
