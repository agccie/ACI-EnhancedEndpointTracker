import {Component, TemplateRef, ViewChild} from '@angular/core';
import {BackendService} from '../../../_service/backend.service';
import {FabricService} from "../../../_service/fabric.service";
import {ModalService} from '../../../_service/modal.service';
import {CommonService} from 'src/app/_service/common.service';

@Component({
    selector: 'app-notification',
    templateUrl: './notification.component.html',
})
export class NotificationComponent {
    isLoading = false;
    modalIconClass = '';
    modalAlertClass = '';
    modalTitle = '';
    modalBody = '';
    modalConfirm = false;
    modalConfirmCallback = undefined;

    constructor(public service: FabricService, private backendService: BackendService, public modalService: ModalService,
                public commonService: CommonService) {}

    // send syslog/email test notification
    testNotification(notifyType : string = '') {
        this.isLoading = true;
        this.backendService.testNotification(this.service.fabric.fabric, notifyType).subscribe(
            (data) => {
                this.isLoading = false;
                this.modalService.setModalSuccess({
                    "body": "Test "+notifyType+" sent. Please validate the message was received."
                })
            }, 
            (error) => {
                this.isLoading = false;
                this.modalService.setModalError({
                    "body": 'Failed test notification. ' + error['error']['error']
                });
            }
        );
    }
}
