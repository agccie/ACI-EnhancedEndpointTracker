import {Component} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {FabricService} from "../../../_service/fabric.service";

@Component({
    selector: 'app-notification',
    templateUrl: './notification.component.html',
})
export class NotificationComponent {

    constructor(public service: FabricService, private backendService: BackendService) {
    }

    testEmailNotifications(type: String, fabricName: String) {
        //todo
    }

}
