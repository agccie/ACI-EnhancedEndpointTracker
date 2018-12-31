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
    modalSubTitle = '';
    modalBody = '';
    modalIcon: String;
    decisionBox = false;
    callback: any;
    callbackContext: any;
    modalConfirm = false;
    modalConfirmCallback = undefined;
    modalHeaderClass = '';
    modalLoading = false;
    generalModal: TemplateRef<any>;

    constructor(private modalService: BsModalService) {
    }


    public setModalSuccess(content: object = {}) {
        this.modalHeaderClass = 'text-secondary';
        if (!("title" in content)) {
            content["title"] = "Success";
        }
        this._openModal(content);
    }

    public setModalInfo(content: object = {}) {
        this.modalHeaderClass = 'text-info';
        if (!("title" in content)) {
            content["title"] = "Info";
        }
        this._openModal(content);
    }

    public setModalWarning(content: object = {}) {
        this.modalHeaderClass = 'text-warning';
        if (!("title" in content)) {
            content["title"] = "Warning";
        }
        this._openModal(content);
    }

    public setModalError(content: object = {}) {
        this.modalHeaderClass = 'text-danger';
        if (!("title" in content)) {
            content["title"] = "Error";
        }
        this._openModal(content);
    }

    public setModalConfirm(content: object = {}) {
        const self = this;
        this.modalConfirmCallback = function () {
            self.hideModal();
            if ("callback" in content) {
                content["callback"]();
            }
        };
        if (!("modalType" in content)) {
            content["modalType"] = "info";
        }
        switch (content["modalType"]) {
            case "success":
                this.setModalSuccess(content);
                break;
            case "info":
                this.setModalInfo(content);
                break;
            case "warning":
                this.setModalWarning(content);
                break;
            case "error":
                this.setModalError(content);
                break;
            default:
                this.setModalInfo(content);
        }
        this.modalConfirm = true;
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
        try{
            this.modalRef.hide();
        }
        catch(error){
            console.log("failed to hide modal: "+error)
        }
    }

    private _openModal(content: object = {}) {
        this.hideModal();
        this.modalConfirm = false;
        ["title", "subtitle", "body", "loading"].forEach(function(attr){
            if(!(attr in content) || typeof(content[attr])==="undefined"){
                if(attr=="loading"){
                    content[attr] = false;
                } else {
                    content[attr] = "";
                }
            }
        })
        this.modalTitle = content["title"];
        this.modalSubTitle = content['subtitle'];
        this.modalBody = content["body"];
        this.modalLoading = content["loading"];
        this.openModal(this.generalModal);
    }
}
