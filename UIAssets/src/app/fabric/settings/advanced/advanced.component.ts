import {Component, OnInit} from '@angular/core';
import {PreferencesService} from "../../../_service/preferences.service";

@Component({
    selector: 'app-advanced',
    templateUrl: './advanced.component.html',
})
export class AdvancedComponent implements OnInit {

    constructor(public prefs: PreferencesService) {
    }

    ngOnInit() {
    }

}
