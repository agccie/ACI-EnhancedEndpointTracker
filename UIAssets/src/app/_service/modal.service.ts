import {Injectable, TemplateRef} from '@angular/core';
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


      setAndOpenModal(modalIcon,modalTitle,modalBody,modalRef:TemplateRef<any>,decisionBox = false,callback=undefined,context=undefined) {
        if(context === undefined) {
            context = this ;
        }
        context.modalIcon = modalIcon ;
        context.modalTitle = modalTitle ;
        context.modalBody = modalBody ;
        context.decisionBox = decisionBox ;
        context.callback = callback ;
        this.openModal(modalRef) ;
    }

    runCallback() {
        if(this.callback !== undefined) {
            this.callback() ;
        }
        
    }

}
