import { BrowserModule } from '@angular/platform-browser';
import { NgModule } from '@angular/core';
import {NgxDatatableModule} from '@swimlane/ngx-datatable' ;
import { AppComponent } from './app.component';
import { FabricsComponent } from './fabrics/fabrics.component';
import {Routes, RouterModule} from '@angular/router';
import { UsersComponent } from './users/users.component';
import { EndpointHistoryComponent } from './endpoint-history/endpoint-history.component';
import { LoginComponent } from './login/login.component'
import {FormsModule, ReactiveFormsModule} from "@angular/forms";
import { MoveEventsComponent } from './endpoint-history/move-events/move-events.component';
import { OffSubnetEventsComponent } from './endpoint-history/off-subnet-events/off-subnet-events.component';
import { StaleEventsComponent } from './endpoint-history/stale-events/stale-events.component';
import { PerNodeHistoryComponent } from './endpoint-history/per-node-history/per-node-history.component';
import {AuthGuardService} from './_service/auth-guard.service' ;
import {AccordionModule, ModalModule, TooltipModule} from "ngx-bootstrap";

const appRoutes: Routes = [
  {path:'login', component:LoginComponent},
  {path:"fabrics" , component: FabricsComponent, canActivate:[AuthGuardService]},
  {path:"users", component: UsersComponent, canActivate:[AuthGuardService]},
  {path:"ephistory/:address", component: EndpointHistoryComponent ,
  canActivate:[AuthGuardService], 
  children:[
    {path:'pernodehistory', component:PerNodeHistoryComponent},
    {path:'moveevents', component: MoveEventsComponent},
    {path:'offsubnetevents',component: OffSubnetEventsComponent},
    {path:'staleevents',component:StaleEventsComponent}
  ]}
  
]

@NgModule({
  declarations: [
    AppComponent,
    FabricsComponent,
    UsersComponent,
    EndpointHistoryComponent,
    LoginComponent,
    PerNodeHistoryComponent,
    MoveEventsComponent,
    OffSubnetEventsComponent,
    StaleEventsComponent
  ],
  imports: [
    BrowserModule,
    NgxDatatableModule,
    RouterModule.forRoot(appRoutes),
    FormsModule,
    ReactiveFormsModule,
    AccordionModule.forRoot()
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule { }
