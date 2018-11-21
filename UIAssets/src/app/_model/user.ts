export class UserList {
    count: number;
    objects: User[];

    public constructor() {
        this.count = 0;
        this.objects = [];
    }
}

export class User {
    username: string;
    role: number;
    password: string;
    last_login: number;
    is_new: boolean;
    password_confirm: string;

    constructor(
        username: string = '',
        role: number = 1,
        password: string = '',
        last_login: number = 0,
        is_new: boolean = true,
        password_confirm: string = ''
    ) {
        this.username = username;
        this.role = role;
        this.password = password;
        this.last_login = last_login;
        this.is_new = is_new;
        this.password_confirm = password_confirm;
    }
}
