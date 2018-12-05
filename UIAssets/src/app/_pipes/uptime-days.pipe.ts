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
        if (seconds < 10) {
            secondsStr = '0';
        }
        secondsStr += seconds;
        return `${Math.trunc(days)} days, ${Math.trunc(hours)}:${Math.trunc(minutes)}:${secondsStr}`;
    }
}
