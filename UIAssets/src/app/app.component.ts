import { Component, ViewChild, OnInit } from '@angular/core';
import { Router } from '../../node_modules/@angular/router';
import { BackendService } from './_service/backend.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit {
  menu:any ;
  currentMenuItem = 0 ;
  cul:string ;
  ls:Storage ;
  constructor(private router : Router, private bs:BackendService) {
    this.menu = [{name:'Fabrics',icon:'icon-computer',active:true},{name:'Users',icon:'icon-user',active:false},{name:'Settings',icon:'icon-cog',active:false}] ;
    this.cul = localStorage.getItem('cul') ;
    this.ls = localStorage ;
  }

  ngOnInit() {
    this.cul = localStorage.getItem('cul') ;
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
        this.cul='0' ;
        this.router.navigate(['login']) ;
      },
    (error)=>{

    }
    )
  }

}
