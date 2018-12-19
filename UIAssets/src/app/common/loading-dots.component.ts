import {Component, Input} from "@angular/core";
import { text } from "@angular/core/src/render3";

@Component({
    selector: 'loading-dots',
    templateUrl: './loading-dots.component.html',
})

export class LoadingDotsComponent {
    @Input() text: string;
}
