import { Pipe, PipeTransform } from '@angular/core';

@Pipe({
  name: 'localNode'
})
export class LocalNodePipe implements PipeTransform {

  transform(value: any, args?: any): any {
    let localNode = '' ;
    if(value > 0xffff){
      const nodeA = (value & 0xffff0000) >> 16;
      const nodeB = (value & 0x0000ffff);
      localNode = `(${nodeA},${nodeB})`;
      }else if(value === 0) {
        return '\u2014' ;
      }else{
        localNode = value ;
      }
      return localNode ;
  }
  

}
