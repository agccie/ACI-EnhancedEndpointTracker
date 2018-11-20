import {Component, OnInit} from '@angular/core';
import {PreferencesService} from '../../_service/preferences.service';

@Component({
    selector: 'app-notification',
    templateUrl: './notification.component.html',
    styleUrls: ['./notification.component.css']
})
export class NotificationComponent implements OnInit {
    inputs = [];

    constructor(public prefs: PreferencesService) {
        this.inputs = [
            {name: 'Email Address', model: 'email_address', type: 'text'},
            {name: 'Syslog Server', model: 'syslog_server', type: 'text'},
            {name: 'Syslog Port', model: 'syslog_port', type: 'number', min: '0', max: '65536'},
            {name: 'Notify moves by email', model: 'notify_move_email', type: 'boolean'},
            {name: 'Log moves to syslog', model: 'notify_move_syslog', type: 'boolean'},
            {name: 'Notify about offsubnet endpoints by email', model: "notify_offsubnet_email", type: 'boolean'},
            {name: 'Log offsubnet endpoints to syslog', model: "notify_offsubnet_syslog", type: 'boolean'},
            {name: 'Notify about stale endpoints by email ', model: "notify_stale_email", type: 'boolean'},
            {name: 'Log stale endpoints to syslog', model: "notify_stale_syslog", type: 'boolean'}
        ]
    }

    ngOnInit() {
    }

}
