import { Injectable } from '@angular/core';
import { CanActivate } from '@angular/router';
import { PreferencesService } from './preferences.service';

@Injectable({
  providedIn: 'root'
})
export class AuthGuardService implements CanActivate{

  constructor(public prefs:PreferencesService) { }

  canActivate():boolean {
    if(localStorage.getItem('cul') === '1') {
      return true ;
    }else{
      return false ;
    }
  }
}
