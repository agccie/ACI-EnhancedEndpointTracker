import {Component, OnInit} from '@angular/core';
import {environment} from '../../../../environments/environment.standalone';
import {FabricService} from "../../../_service/fabric.service";

@Component({
    selector: 'app-connectivity',
    templateUrl: './connectivity.component.html',
})

export class ConnectivityComponent {
    app_mode = environment.app_mode;
    constructor(public service: FabricService) {}
}
