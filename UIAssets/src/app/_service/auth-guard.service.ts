import { Injectable } from '@angular/core';
import { CanActivate } from '../../../node_modules/@angular/router';

@Injectable({
  providedIn: 'root'
})
export class AuthGuardService implements CanActivate{

  constructor() { }

  canActivate():boolean {
    if(localStorage.getItem('cul') === '1') {
      return true ;
    }else{
      return false ;
    }
  }
}
