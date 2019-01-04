import {Component} from '@angular/core';
import {environment} from '../../../../environments/environment';
import {FabricService} from "../../../_service/fabric.service";

@Component({
    selector: 'app-connectivity',
    templateUrl: './connectivity.component.html',
})

export class ConnectivityComponent {
    app_mode: boolean = false;

    constructor(public service: FabricService) {
        this.app_mode = environment.app_mode;
    }
}
