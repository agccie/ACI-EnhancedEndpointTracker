import {Pipe, PipeTransform} from '@angular/core';

@Pipe({
    name: 'uptimeDays'
})

export class UptimeDaysPipe implements PipeTransform {
    transform(value: any, args?: any): any {
        let days = value / (24 * 3600);
        let hours = (value % (24 * 3600)) / 3600;
        let minutes = ((hours % 1) * 60);
        let secondsStr = Math.trunc((minutes % 1) * 60).toString().padStart(2, '0');
        let minutesStr = Math.trunc(minutes).toString().padStart(2, '0');
        let hoursStr = Math.trunc(hours).toString().padStart(2, '0');
        return `${Math.trunc(days)} days, ${hoursStr}:${minutesStr}:${secondsStr}`;
    }
}
