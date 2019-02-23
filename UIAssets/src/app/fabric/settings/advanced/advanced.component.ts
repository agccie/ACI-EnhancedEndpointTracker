import {Component} from '@angular/core';
import {FabricService} from "../../../_service/fabric.service";

@Component({
    selector: 'app-advanced',
    templateUrl: './advanced.component.html',
})

export class AdvancedComponent {

    constructor(public service: FabricService) {
    }
}
