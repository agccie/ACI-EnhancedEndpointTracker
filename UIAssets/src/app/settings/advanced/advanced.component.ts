import {Component, OnInit} from '@angular/core';
import {PreferencesService} from '../../_service/preferences.service';

@Component({
    selector: 'app-advanced',
    templateUrl: './advanced.component.html',
    styleUrls: ['./advanced.component.css']
})
export class AdvancedComponent implements OnInit {
    inputs = [];

    constructor(public prefs: PreferencesService) {
        this.inputs = [
            {name: 'Analyze moves', model: "analyze_move", type: 'boolean'},
            {name: 'Analyze offsubnet endpoints', model: 'analyze_offsubnet', type: 'boolean'},
            {name: 'Analyze stale endpoints', model: "analyze_stale", type: 'boolean'},
            {name: 'Maximum endpoint events', model: "max_endpoint_events", type: 'number', min: '0', max: '64'},
            {
                name: 'Maximum per node enpoint events',
                model: "max_per_node_endpoint_events",
                type: 'number',
                min: '0',
                max: '64'
            },
            {name: 'Initialize epm events queue', model: "queue_init_epm_events", type: 'boolean'},
            {name: 'Initialize events queue', model: "queue_init_events", type: 'boolean'}
        ]
    }

    ngOnInit() {
    }

    onFormChange(event) {
        console.log(event);
    }

}
