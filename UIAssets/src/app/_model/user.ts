

export const UserRoles = [
    {"id": 0, "name": "Admin"},
    {"id": 1, "name": "User"},
    {"id": 2, "name": "Blacklist"},
]

let UserRolesMap = {}
UserRoles.forEach(elem=>{
    UserRolesMap[elem.id] = elem.name
})

export class UserList {
    count: number;
    objects: User[];

    public constructor(data) {
        this.count = 0;
        this.objects = [];
        if ("count" in data) {
            this.count = data["count"];
        }
        if ("objects" in data) {
            data["objects"].forEach(obj => {
                if ('user' in obj) {
                    this.objects.push(new User(obj['user']));
                }
            });
        }
    }
}

export class User {
    username: string;
    role: number;
    roleName: string;
    password: string;
    last_login: number;
    is_new: boolean;
    password_confirm: string;

    constructor(data: any = {}) {
        this.init();
        this.sync(data);
    }

    init(){
        this.username = '';
        this.role = 1;
        this.password = '';
        this.password_confirm = '';
        this.is_new = false;
        this.roleName = "-";
        this.last_login = 0;
    }

    // sync to provided JSON
    sync(data: any = {}) {
        for (let attr in data) {
            if (attr in this) {
                if(typeof(data[attr])==="string" && data[attr].length==0){
                    continue;
                }
                this[attr] = data[attr];
            }
        }
        //map role to role name
        if(this.role in UserRoles){
            this.roleName = UserRolesMap[this.role];
        } 
    }

    clone(){
        return new User(this.get_save_json());
    }

    // not all attributes of this object are used for create/update operatons, this function
    // will return a JSON object with writeable attributes only. Additionally, only attributes
    // that are set (non-emptry string) are returned.
    get_save_json(): object {
        let attr = [
            "username",
            "password",
            "role"
        ];
        let json = {};
        for (let i = 0; i < attr.length; i++) {
            let a = attr[i];
            if (a in this) {
                if (typeof this[a] === 'string' && this[a].length == 0){
                    //skip string attributes that are not set
                    continue;
                }
                json[a] = this[a];
            }
        }
        return json;
    }
}
