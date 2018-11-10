import { Component, OnInit } from '@angular/core';
import { Router } from '../../../node_modules/@angular/router';
import { BackendService } from '../_service/backend.service';
import { PreferencesService } from '../_service/preferences.service';
import { AppComponent } from '../app.component';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css']
})
export class LoginComponent implements OnInit {
  title:string ;
  username='' ;
  password='';
  showModal=false;
  modalTitle='' ;
  modalBody='' ;
  version='Not Available' ;
  constructor(private router : Router,private bs : BackendService,private prefs:PreferencesService) {
    this.title = 'Endpoint Tracker'
    this.getAppVersion() ;
   }

  ngOnInit() {
  }
  onSubmit() {
    this.bs.login(this.username,this.password).subscribe(
      (data)=>{
        if(data['success'] === true) { 
        localStorage.setItem('cul','1') ;
        localStorage.setItem('userName',this.username) ;
        this.bs.getUserDetails(this.username).subscribe((response) => {
          const userDetails = response['objects'][0]['user'];
          localStorage.setItem('userRole', userDetails['role']);
        }, (error) => {
          console.error('Could not get user details');
        });
        this.prefs.cul = 1 ;
        this.router.navigate(['fabrics'])
        }
      },
      (error)=>{
      console.log(error) ;
      this.modalTitle = 'Login Error' ;
      this.modalBody =  error['error']['error'] ;
      this.showModal = true ;
      }
    )
    
  }

  logout(){
    this.bs.logout().subscribe(
      (data)=>{
        console.log(data) ;
        localStorage.removeItem('cul') ;
        this.prefs.cul = 1 ;
        this.router.navigate(['/']) ;
      },
    (error)=>{
      this.modalTitle = 'Logout Error' ;
      this.modalBody = error['error']['error'] ;
      this.showModal = true ;
    }
    )
  }

  getAppVersion() {
    this.bs.getAppVersion().subscribe(
      (data)=>{
        this.version = data['version'];
      },
      (error)=>{
        this.modalTitle = 'Version Error' ;
      this.modalBody = error['error'] ;
      this.showModal = true ;
      }
    )
  }

}
