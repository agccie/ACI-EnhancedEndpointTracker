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
import { FabricOverviewComponent } from './fabrics/fabric-overview/fabric-overview.component';
import { EndpointsComponent } from './fabrics/endpoints/endpoints.component';
import { HistoryComponent } from './fabrics/history/history.component';
import { MovesComponent } from './fabrics/moves/moves.component';
import { StaleEptComponent } from './fabrics/stale-ept/stale-ept.component';
import { OffsubnetEptComponent } from './fabrics/offsubnet-ept/offsubnet-ept.component';

const appRoutes: Routes = [
  {path:'login', component:LoginComponent},
  {path:"fabrics" , component: FabricsComponent, canActivate:[AuthGuardService],
  children:[
    {path:'fabric-overview',component:FabricOverviewComponent},
    {path:'endpoints',component:EndpointsComponent},
    {path:'latest-events',component:HistoryComponent},
    {path:'moves',component:MovesComponent},
    {path:'stale-endpoints',component:StaleEptComponent},
    {path:'offsubnet-endpoints',component:OffsubnetEptComponent}
  ]},
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
    StaleEventsComponent,
    FabricOverviewComponent,
    EndpointsComponent,
    HistoryComponent,
    MovesComponent,
    StaleEptComponent,
    OffsubnetEptComponent
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
