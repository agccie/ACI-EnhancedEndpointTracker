import {Component, Input} from "@angular/core";

@Component({
    selector: 'loading-dots',
    templateUrl: './loading-dots.component.html',
})

export class LoadingDotsComponent {
    @Input() text: string;
}
