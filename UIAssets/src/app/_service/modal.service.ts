import {Injectable, TemplateRef, Component} from '@angular/core';
import {BsModalRef, BsModalService} from 'ngx-bootstrap';

@Injectable({
    providedIn: 'root'
})

export class ModalService {
    modalRef: BsModalRef;
    modalClass = 'modal-sm';
    template: TemplateRef<any>;
    modalTitle: String;
    modalBody: String;
    modalIcon: String;
    decisionBox = false ;
    callback:any ;
    callbackContext:any ;

    constructor(private modalService: BsModalService) {
        this.modalTitle = 'Error';
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

    setAndOpenModal(modalIcon, modalTitle, modalBody, modalRef: TemplateRef<any>, decisionBox = false, callback = undefined, context = undefined) {
        if (context === undefined) {
            context = this;
        }
        this.modalIcon = modalIcon ;
        this.modalTitle = modalTitle ;
        this.modalBody = modalBody ;
        this.decisionBox = decisionBox ;
        context.decisionBox = decisionBox ;
        this.template = modalRef ;
        context.callback = callback ;
        this.callback = callback;
        this.callbackContext = context ;
        this.template = modalRef ;
        this.openModal(modalRef) ;
    }

    runCallback() {
        if(this.callback !== undefined) {
            this.callbackContext.callback() ;
        }
    }
}
