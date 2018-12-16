import {Injectable, TemplateRef} from '@angular/core';
import {BsModalRef, BsModalService} from 'ngx-bootstrap';

@Injectable({
    providedIn: 'root'
})

export class ModalService {
    modalRef: BsModalRef;
    modalClass = 'modal-sm';
    template: TemplateRef<any>;
    modalTitle = '';
    modalBody = '';
    modalIcon: String;
    decisionBox = false;
    callback: any;
    callbackContext: any;
    modalConfirm = false;
    modalConfirmCallback = undefined;
    modalIconClass = '';
    modalAlertClass = '';
    generalModal: TemplateRef<any>;

    constructor(private modalService: BsModalService) {
        this.modalTitle = 'Error';
    }

    setAndOpenModal(modalIcon, modalTitle, modalBody, modalRef: TemplateRef<any>, decisionBox = false, callback = undefined, context = undefined) {
        if (context === undefined) {
            context = this;
        }
        this.modalIcon = modalIcon;
        this.modalTitle = modalTitle;
        this.modalBody = modalBody;
        this.decisionBox = decisionBox;
        context.decisionBox = decisionBox;
        this.template = modalRef;
        context.callback = callback;
        this.callback = callback;
        this.callbackContext = context;
        this.template = modalRef;
        this.openModal(modalRef);
    }

    runCallback() {
        if (this.callback !== undefined) {
            this.callbackContext.callback();
        }
    }
    
    public setModalError(content : object = {}) {
        this.modalAlertClass='alert alert--danger';
        this.modalIconClass='alert__icon icon-error-outline';
        if(!("title" in content)){
            content["title"] = "Error";
        }
        this._openModal(content);
    }
    
    public setModalSuccess(content : object = {}){
        this.modalAlertClass='alert alert--success';
        this.modalIconClass='alert__icon icon-check-outline';
        if(!("title" in content)){
            content["title"] = "Success";
        }
        this._openModal(content);
    }
    
    public setModalInfo(content : object = {}){
        this.modalAlertClass='alert';
        this.modalIconClass='alert__icon icon-info-outline';
        if(!("title" in content)){
            content["title"] = "Info";
        }
        this._openModal(content);
    }
    
    public setModalConfirm(content : object = {}){
        this.modalConfirmCallback = function(){
            this.hideModal();
            if("callback" in content){
                content["callback"]();
            }
        }
        if(!("modalType" in content)){
            content["modalType"] = "info";
        }
        switch(content["modalType"]){
            case "success": this.setModalSuccess(content);
                            break;
            case "info": this.setModalInfo(content); 
                        break;
            case "error": this.setModalError(content);
                        break;
            default: this.setModalInfo(content);
        }
        this.modalConfirm = true;
    }

    private _openModal(content: object = {}){
        this.modalConfirm = false;
        this.modalTitle = content["title"];
        this.modalBody = content["body"];
        this.openModal(this.generalModal);
    }

    public openModal(template: TemplateRef<any>) {
        this.modalRef = this.modalService.show(template, {
            animated: true,
            keyboard: true,
            backdrop: true,
            ignoreBackdropClick: false,
            class: this.modalClass,
        });
    }

    public hideModal() {
        this.modalRef.hide();
    }
}
