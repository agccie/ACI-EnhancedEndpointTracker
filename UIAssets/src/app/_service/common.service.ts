import {Injectable} from '@angular/core';

@Injectable({
    providedIn: 'root'
})

export class CommonService{

    //common loader html
    public getLoadingHtml() : string{
        return '<div class="loading-dots loading-dots--info">'+
                    '<span></span><span></span><span></span>' +
                '</div>';
    }

    //return cisco-ui class label for endpoint type
    public getEndpointTypeLabel(type:string) : string{
        let label = "label label--raised "
        switch(type){
            case "mac": 
                label+="label--warning-alt";
                break
            case "ipv4": 
                label+="label--vibblue";
                break;
            case "ipv6": 
                label+="label--indigo";
                break;
            default: 
                label+="label--info";
        }
        return label
    }
}