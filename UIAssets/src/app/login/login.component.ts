import { Component, OnInit } from '@angular/core';
import { Router } from '../../../node_modules/@angular/router';
import { BackendService } from '../_service/backend.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css']
})
export class LoginComponent implements OnInit {
  title:string ;
  username='' ;
  password='';
  constructor(private router : Router,private bs : BackendService) {
    this.title = 'Enhanced Endpoint Tracker'
   }

  ngOnInit() {
  }
  onSubmit() {
    this.bs.login(this.username,this.password).subscribe(
      (data)=>{
        if(data['success'] === true) { 
        localStorage.setItem('cul','1') ;
        this.router.navigate(['fabrics'])
        }
      },
      (error)=>{
        console.log(error) ;
      }
    )
    
  }

  logout(){
    this.bs.logout().subscribe(
      (data)=>{
        console.log(data) ;
        localStorage.removeItem('cul') ;
        this.router.navigate(['/']) ;
      },
    (error)=>{

    }
    )
  }

}
