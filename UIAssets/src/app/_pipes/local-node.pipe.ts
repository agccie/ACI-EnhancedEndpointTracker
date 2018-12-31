import {Pipe, PipeTransform} from '@angular/core';
import {nodeToString} from '../_model/endpoint';

@Pipe({
    name: 'localNode'
})

export class LocalNodePipe implements PipeTransform {
    transform(value: number, tunnelFlags:string[]=[]): string {
        return nodeToString(value, tunnelFlags);
    }
}
