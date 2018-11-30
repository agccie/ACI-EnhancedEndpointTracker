import {BrowserModule} from '@angular/platform-browser';
import {NgModule} from '@angular/core';
import {NgxDatatableModule} from '@swimlane/ngx-datatable';
import {AppComponent} from './app.component';
import {FabricsComponent} from './fabric/fabrics.component';
import {RouterModule, Routes} from '@angular/router';
import {UsersComponent} from './users/users.component';
import {EndpointHistoryComponent} from './fabric/history/endpoint-history.component';
import {LoginComponent} from './login/login.component'
import {FormsModule, ReactiveFormsModule} from '@angular/forms';
import {MoveEventsComponent} from './fabric/history/move-events/move-events.component';
import {OffSubnetEventsComponent} from './fabric/history/off-subnet-events/off-subnet-events.component';
import {StaleEventsComponent} from './fabric/history/stale-events/stale-events.component';
import {PerNodeHistoryComponent} from './fabric/history/per-node-history/per-node-history.component';
import {AuthGuardService} from './_service/auth-guard.service';
import {AccordionModule, ModalModule, TypeaheadModule} from 'ngx-bootstrap';
import {EndpointsComponent} from './fabric/endpoint/endpoints.component';
import {EventComponent} from './fabric/event/event.component';
import {MovesComponent} from './fabric/moves/moves.component';
import {StaleEptComponent} from './fabric/stale-ept/stale-ept.component';
import {OffsubnetEptComponent} from './fabric/offsubnet-ept/offsubnet-ept.component';
import {BackendService} from './_service/backend.service';
import {HTTP_INTERCEPTORS, HttpClientModule} from '@angular/common/http';
import {MomentModule} from 'ngx-moment';
import {NgSelectModule} from '@ng-select/ng-select';
import {NgbModule} from '@ng-bootstrap/ng-bootstrap';
import {BackendInterceptorService} from './_service/backend-interceptor.service';
import {CookieService} from 'ngx-cookie-service';
import {HashLocationStrategy, LocationStrategy} from '@angular/common';
import {LocalLearnsComponent} from './fabric/history/local-learns/local-learns.component';
import {WelcomeComponent} from "./welcome/welcome.component";
import {SettingsComponent} from "./fabric/settings/settings.component";
import {ConnectivityComponent} from "./fabric/settings/connectivity/connectivity.component";
import {NotificationComponent} from "./fabric/settings/notification/notification.component";
import {RemediationComponent} from "./fabric/settings/remediation/remediation.component";
import {AdvancedComponent} from "./fabric/settings/advanced/advanced.component";
import {OverviewComponent} from "./fabric/overview/overview.component";
import {NotFoundComponent} from "./notfound/notfound.component";
import {QueueComponent} from "./queue/queue.component";
import {QueueDetailComponent} from "./queue-detail/queue-detail.component";
import {HighchartsChartModule} from "highcharts-angular";
import {QueryBuilderModule} from "angular2-query-builder";
import { RapidEptComponent } from './fabric/rapid-ept/rapid-ept.component';
import { ClearedEptComponent } from './fabric/cleared-ept/cleared-ept.component';


const appRoutes: Routes = [
    {
        path: 'login',
        component: LoginComponent,
    },
    {
        path: '',
        canActivate: [AuthGuardService],
        children: [
            {path: '', component: WelcomeComponent}
        ]
    },
    {
        path: 'fabric/:fabric',
        component: FabricsComponent,
        canActivate: [AuthGuardService],
        children: [
            {path: '', component: OverviewComponent},
            {path: 'endpoints', component: EndpointsComponent},
            {path: 'events', component: EventComponent},
            {path: 'moves', component: MovesComponent},
            {path: 'stale-endpoints', component: StaleEptComponent},
            {path: 'offsubnet-endpoints', component: OffsubnetEptComponent},
            {path:'rapid-endpoints', component:RapidEptComponent},
            {path:'cleared-endpoints',component:ClearedEptComponent},
            {
                path: 'settings',
                component: SettingsComponent,
                children: [
                    {path: 'connectivity', component: ConnectivityComponent},
                    {path: 'notification', component: NotificationComponent},
                    {path: 'remediation', component: RemediationComponent},
                    {path: 'advanced', component: AdvancedComponent}
                ]
            },
            {
                path: 'history/:vnid/:address',
                component: EndpointHistoryComponent,
                children: [
                    {path: '', redirectTo: 'locallearns', pathMatch: 'full'},
                    {path: 'locallearns', component: LocalLearnsComponent},
                    {path: 'pernodehistory', component: PerNodeHistoryComponent},
                    {path: 'moveevents', component: MoveEventsComponent},
                    {path: 'offsubnetevents', component: OffSubnetEventsComponent},
                    {path: 'staleevents', component: StaleEventsComponent}
                ]
            }
        ]
    },
    {
        path: 'users',
        component: UsersComponent,
        canActivate: [AuthGuardService]
    },
    {
        path: 'queues',
        component: QueueComponent,
        canActivate: [AuthGuardService]
    },
    {
        path: 'queue/:dn',
        component: QueueDetailComponent,
        canActivate: [AuthGuardService]
    },
    {path: '**', component: NotFoundComponent},
];

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
        EndpointsComponent,
        EventComponent,
        MovesComponent,
        StaleEptComponent,
        OffsubnetEptComponent,
        SettingsComponent,
        ConnectivityComponent,
        NotificationComponent,
        RemediationComponent,
        AdvancedComponent,
        LocalLearnsComponent,
        WelcomeComponent,
        OverviewComponent,
        NotFoundComponent,
        RapidEptComponent,
        ClearedEptComponent,
        NotFoundComponent,
        QueueComponent,
        QueueDetailComponent
    ],
    imports: [
        BrowserModule,
        NgxDatatableModule,
        RouterModule.forRoot(appRoutes),
        FormsModule,
        ReactiveFormsModule,
        AccordionModule.forRoot(),
        HttpClientModule,
        MomentModule,
        NgSelectModule,
        HighchartsChartModule,
        NgbModule.forRoot(),
        TypeaheadModule.forRoot(),
        ModalModule.forRoot(),
        QueryBuilderModule,
    ],
    providers: [
        BackendService,
        CookieService,
        {provide: HTTP_INTERCEPTORS, useClass: BackendInterceptorService, multi: true},
        {provide: LocationStrategy, useClass: HashLocationStrategy}
    ],
    bootstrap: [AppComponent]
})
export class AppModule {
}
