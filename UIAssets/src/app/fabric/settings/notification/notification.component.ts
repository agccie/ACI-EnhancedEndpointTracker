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
    @ViewChild('generalModal') msgModal: TemplateRef<any>;
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
                this.setModalSuccess({
                    "body": "Test "+notifyType+" sent. Please validate the message was received."
                })
            }, 
            (error) => {
                this.isLoading = false;
                this.setModalError({
                    "body": 'Failed test notification. ' + error['error']['error']
                });
            }
        );
    }

    openModal(content: object = {}){
        this.modalConfirm = false;
        this.modalTitle = content["title"];
        this.modalBody = content["body"];
        this.modalService.openModal(this.msgModal);
    }
    setModalError(content : object = {}) {
        this.modalAlertClass='alert alert--danger';
        this.modalIconClass='alert__icon icon-error-outline';
        if(!("title" in content)){
            content["title"] = "Error";
        }
        this.openModal(content);
    }
    setModalSuccess(content : object = {}){
        this.modalAlertClass='alert alert--success';
        this.modalIconClass='alert__icon icon-check-outline';
        if(!("title" in content)){
            content["title"] = "Success";
        }
        this.openModal(content);
    }
    setModalInfo(content : object = {}){
        this.modalAlertClass='alert';
        this.modalIconClass='alert__icon icon-info-outline';
        if(!("title" in content)){
            content["title"] = "Info";
        }
        this.openModal(content);
    }
    setModalConfirm(content : object = {}){
        this.modalConfirmCallback = function(){
            this.modalService.hideModal();
            if("callback" in content){
                content["callback"]();
            }
        }
        this.setModalInfo(content);
        this.modalConfirm = true;
    }
}
