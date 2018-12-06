import {Pipe, PipeTransform} from '@angular/core';

@Pipe({
    name: 'uptimeDays'
})

export class UptimeDaysPipe implements PipeTransform {
    transform(value: any, args?: any): any {
        let days = value / (24 * 3600);
        let hours = (value % (24 * 3600)) / 3600;
        let minutes = ((hours % 1) * 60);
        let seconds = Math.trunc((minutes % 1) * 60);
        let secondsStr = '';
        let hoursStr = '' ;
        let minutesStr = '' ;
        if (seconds < 10) {
            secondsStr = '0';
        }
        if (minutes < 10) {
            minutesStr = '0';
        }
        if(hours < 10) {
            hoursStr = '0';
        }
        secondsStr += seconds;
        minutesStr += Math.trunc(minutes) ;
        hoursStr += Math.trunc(hours);
        return `${Math.trunc(days)} days, ${hoursStr}:${minutesStr}:${secondsStr}`;
    }
}
