import {Component} from '@angular/core';
import {FabricService} from "../../../_service/fabric.service";

@Component({
    selector: 'app-remediation',
    templateUrl: './remediation.component.html',
})
export class RemediationComponent {
    constructor(public service: FabricService) {}

}
