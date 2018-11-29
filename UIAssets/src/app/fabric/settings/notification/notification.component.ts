import {Component, OnInit} from '@angular/core';
import {PreferencesService} from "../../../_service/preferences.service";
import { BackendService } from '../../../_service/backend.service';

@Component({
    selector: 'app-notification',
    templateUrl: './notification.component.html',
})
export class NotificationComponent implements OnInit {
    

    constructor(public prefs: PreferencesService, private backendService:BackendService) {
      
    }

    ngOnInit() {
    }

    testEmailNotifications(type:String,fabricName:String) {
        this.backendService.testEmailNotifications(type,fabricName).subscribe(
            (data)=>{

            },
            (error)=>{

            }
        )
    }

}
