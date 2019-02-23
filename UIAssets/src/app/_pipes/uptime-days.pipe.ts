import {Pipe, PipeTransform} from '@angular/core';

@Pipe({
    name: 'uptimeDays'
})

export class UptimeDaysPipe implements PipeTransform {
    transform(value: string): string {
        let ts = parseInt(value);
        let d = Math.floor(ts/86400);
        let s = ts%60;
        let h = 0;
        let m = 0;
        if(ts-d*86400>0){
            h = Math.floor((ts-d*86400)/3600);
        }
        if(ts-d*86400-h*3600 > 0){
            m = Math.floor((ts-d*86400-h*3600)/60);
        }
        return d+" days, "+(""+h).padStart(2,'0')+":"+(""+m).padStart(2,'0')+":"+(""+s).padStart(2,'0')
    }
}
