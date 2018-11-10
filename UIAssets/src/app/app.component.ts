import { Component, ViewChild, OnInit } from '@angular/core';
import { Router } from '../../node_modules/@angular/router';
import { BackendService } from './_service/backend.service';
import { PreferencesService } from './_service/preferences.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit {
  menu:any ;
  currentMenuItem = 0 ;
  cul:number ;
  ls:Storage ;
  constructor(private router : Router, private bs:BackendService, public prefs:PreferencesService ){
    this.menu = [{name:'Fabrics',icon:'icon-computer',active:true},{name:'Users',icon:'icon-user',active:false},{name:'Settings',icon:'icon-cog',active:false}] ;
    this.cul = this.prefs.cul ;
  }

  ngOnInit() {
    
  }

  onMenuItemSelect(index) {
    this.menu[this.currentMenuItem].active = false;
    this.menu[index].active = true ;
    this.currentMenuItem = index ;
  }

  logout(){
    this.bs.logout().subscribe(
      (data)=>{
        console.log(data) ;
        localStorage.setItem('cul','0') ;
        this.prefs.cul=0 ;
        this.router.navigate(['/']) ;
      },
    (error)=>{
      this.prefs.cul=0 ;
        this.router.navigate(['/']) ;
    }
    )
  }

}
