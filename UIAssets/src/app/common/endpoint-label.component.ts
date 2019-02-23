import {Component, Input} from "@angular/core";

@Component({
    selector: 'endpoint-label',
    templateUrl: './endpoint-label.component.html',
})

export class EndpointLabelComponent {
    @Input() type: string;
}
