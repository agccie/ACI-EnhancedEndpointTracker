import { Injectable , TemplateRef} from '@angular/core';
import { BsModalService, BsModalRef } from '../../../node_modules/ngx-bootstrap';

@Injectable({
  providedIn: 'root'
})
export class ModalService {
  modalRef:BsModalRef ;
  modalClass='modal-sm';
  template: TemplateRef<any> ;
  modalTitle:String;
  modalBody:String;
  modalIcon:String ;
  constructor(private modalService : BsModalService) { 
    this.modalTitle = 'Error' ;
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
