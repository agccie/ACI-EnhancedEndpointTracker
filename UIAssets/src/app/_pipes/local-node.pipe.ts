import {Pipe, PipeTransform} from '@angular/core';

@Pipe({
    name: 'localNode'
})

export class LocalNodePipe implements PipeTransform {
    transform(value: number, tunnelFlags:string[]=[]): string {
        let localNode = '-';
        if (value > 0xffff) {
            const nodeA = (value & 0xffff0000) >> 16;
            const nodeB = (value & 0x0000ffff);
            localNode = `(${nodeA},${nodeB})`;
        } else if (value === 0) {
            localNode = '-';
            //set localNode to proxy if 'proxy' set in any of the provided tunnel flags
            tunnelFlags.forEach(element =>{
                if(element.includes("proxy")){
                    localNode=element;
                }
            })
        } else {
            localNode = ""+value;
        }
        return localNode;
    }
}
