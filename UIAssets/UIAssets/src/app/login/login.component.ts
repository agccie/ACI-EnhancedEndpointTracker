import { Component, OnInit } from '@angular/core';
import { Router } from '../../../node_modules/@angular/router';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css']
})
export class LoginComponent implements OnInit {
  title:string ;
  constructor(private router : Router) {
    this.title = 'Enhanced Endpoint Tracker'
   }

  ngOnInit() {
  }
  onSubmit() {
    localStorage.setItem('cul','1') ;
    this.router.navigate(['fabrics'])
  }

}
