import {Component, Input} from "@angular/core";

@Component({
    selector: 'status-label',
    templateUrl: './status-label.component.html',
})

export class StatusLabelComponent {
    @Input() status: string;

    getLabelClass(){
        switch(this.status){
            case "active": 
                return "label--vibblue";
            case "inactive": 
                return "label--dkgray";
            case "offsubnet": 
                return "label--danger";
            case "rapid": 
                return "label--danger";
            case "stale": 
                return "label--danger";
            case "running":
                return "label--success";
            case "stopped":
                return "label--dkgray";
            case "initializing":
                return "label--default";
            case "starting":
                return "label--info";
            case "failed":
                return "label--warning";
        }
        return "label--default";
    }
}
