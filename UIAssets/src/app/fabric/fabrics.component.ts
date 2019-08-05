import {Component, OnInit, OnDestroy, ViewEncapsulation, ViewChild} from '@angular/core';
import {BackendService} from '../_service/backend.service';
import {ActivatedRoute, Router} from '@angular/router';
import {PreferencesService} from '../_service/preferences.service';
import {ModalService} from "../_service/modal.service";
import {QueryBuilderConfig} from "angular2-query-builder";
import {FormBuilder, FormControl} from "@angular/forms";
import {concat, Observable, of, Subject} from "rxjs";
import {catchError, debounceTime, distinctUntilChanged, switchMap} from "rxjs/operators";
import {repeatWhen, retryWhen, tap, delay, takeUntil} from "rxjs/operators";
import {NgSelectComponent} from '@ng-select/ng-select';
import {EndpointList, Endpoint} from '../_model/endpoint';
import {FabricService} from "../_service/fabric.service";

@Component({
    encapsulation: ViewEncapsulation.None,
    selector: 'app-fabrics',
    templateUrl: './fabrics.component.html',
    styleUrls: ['./fabrics.component.css']
})

export class FabricsComponent implements OnInit, OnDestroy {
    managerRunning: boolean = true;
    @ViewChild('endpointSearch') public ngSelect: NgSelectComponent;
    fabricName: string;
    currentConfig: QueryBuilderConfig;
    queryCtrl: FormControl;
    config: QueryBuilderConfig = {
        fields: {
            address: {name: 'Address', type: 'string'},
            node: {name: 'Node', type: 'number'},
            type: {
                name: 'Type',
                type: 'category',
                options: [
                    {name: 'IPv4', value: 'ipv4'},
                    {name: 'IPv6', value: 'ipv6'},
                    {name: 'MAC', value: 'mac'},
                ]
            },
            stale: {name: 'Stale', type: 'boolean'},
            timestamp: {
                name: 'Timestamp', type: 'date', operators: ['=', '<=', '>'],
                defaultValue: (() => new Date())
            },
        }
    };
    query: any = {
        condition: 'and',
        rules: [
            {field: 'address', operator: '='},
        ]
    };
    queryText: string;

    // search bar variables
    selectedEp: any;
    endpoints$: Observable<any>;
    endpointInput$ = new Subject<string>();
    endpointLoading: boolean = false;
    endpointList = [];
    endpointMatchCount: number = 0;
    endpointHeader: boolean = false;
    fabricRunning: boolean = true;
    private onDestroy$ = new Subject<boolean>();

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, 
                private activatedRoute: ActivatedRoute, public fabricService: FabricService, public modalService: ModalService, 
                private formBuilder: FormBuilder) {
        this.queryText = '';
    }

    ngOnInit(): void {
        this.activatedRoute.paramMap.subscribe(params => {
            this.fabricName = params.get('fabric');
            this.queryCtrl = this.formBuilder.control(this.query);
            this.currentConfig = this.config;
            this.fabricService.fabric.init();
            this.fabricService.fabric.fabric = this.fabricName;
            this.backgroundPollFabricStatus();
        });
        this.searchEndpoint();
        this.backgroundPollManagerStatus();
    }

    ngOnDestroy(): void {
        this.onDestroy$.next(true);
        this.onDestroy$.complete();
    }

    updateQueryText() {
        this.queryText = this.queryToText();
    }

    private valueToSQL(value) {
        switch (typeof value) {
            case 'string':
                return "'" + value + "'";
            case 'boolean':
                return value ? 'true' : 'false';
            case 'number':
                if (isFinite(value)) return value;
        }
    }

    private isDefined(value) {
        return value !== undefined;
    }

    private queryToText(ruleset = this.query) {
        return ruleset.rules.map((rule) => {
            if (rule.rules) {
                return "(" + this.queryToText(rule) + ")";
            }
            var column = rule.field, operator, value;
            switch (rule.operator) {
                case "is null":
                case "is not null":
                    operator = rule.operator;
                    value = "";
                    break;
                case "in":
                case "not in":
                    operator = rule.operator;
                    if (Array.isArray(rule.value) && rule.value.length)
                        value = "(" + rule.value.map(this.valueToSQL).filter(this.isDefined).join(", ") + ")";
                    break;
                default:
                    operator = rule.operator;
                    value = this.valueToSQL(rule.value);
                    break;
            }
            if (this.isDefined(column) && this.isDefined(value) && this.isDefined(operator)) {
                return "(" + (column + " " + operator + " " + value).trim() + ")";
            }
        }).filter(this.isDefined).join(" " + ruleset.condition + " ");
    }

    public onEndPointChange(endpoint) {
        this.endpointList = [];
        this.endpointMatchCount = 0;
        this.endpointHeader = false;
        if(endpoint && "vnid" in endpoint && endpoint.vnid>0){
            this.ngSelect.clearModel();
            this.router.navigate(['/fabric', endpoint.fabric, 'history', endpoint.vnid, endpoint.addr]);
        } else if (typeof(endpoint)!=="undefined"){  
            this.ngSelect.clearModel();
        }
    }

    private searchEndpoint() {
        this.endpoints$ = concat(
            of([]), // default items
            this.endpointInput$.pipe(
                debounceTime(200),
                distinctUntilChanged(),
                tap(() => {
                    this.endpointLoading = true;
                    this.endpointMatchCount = 0;
                    this.endpointList = [];
                }),
                switchMap(term => this.backendService.searchEndpoint(term, this.fabricName).pipe(
                    catchError(() => of([])), // empty list on error
                    tap(() => {
                        this.endpointLoading = false;
                    })
                ))
            )
        );
        this.endpoints$.subscribe(
            (data) => {
                if("objects" in data){
                    let endpoint_list = new EndpointList(data);
                    this.endpointList = endpoint_list.objects;
                    this.endpointMatchCount = endpoint_list.count;
                    this.endpointHeader = true;
                    if(this.endpointList.length==0){
                        //dummy result to hide 'not found' error on valid search (we have match count=0 already displayed)
                        this.endpointList = [new Endpoint()]
                    }
                } else {
                    //search was not performed
                    this.endpointList = [];
                    this.endpointMatchCount = 0;
                    this.endpointHeader = false;
                }          
            }
        );
    }

    // sliently manager status at regular interval
    private backgroundPollManagerStatus(){
        this.backendService.getAppManagerStatus().pipe(
            repeatWhen(delay(10000)),
            takeUntil(this.onDestroy$),
            retryWhen( error => error.pipe(
                tap(val => {
                    console.log("manager refresh error occurred");
                }),
                delay(1000)
            ))
        ).subscribe(
            (data) => {
                if("manager" in data && "status" in data["manager"] && data["manager"]["status"] == "running"){
                    this.managerRunning = true;
                } else {
                    this.managerRunning = false;
                }
            }
        );
    }

    // sliently update fabric service status at regular interval
    private backgroundPollFabricStatus(){
        this.backendService.getFabricStatus(this.fabricService.fabric).pipe(
            repeatWhen(delay(2500)),
            takeUntil(this.onDestroy$),
            retryWhen( error => error.pipe(
                tap(val => {
                    console.log("fabric status refresh error occurred");
                }),
                delay(5000)
            ))
        ).subscribe(
            (fabricStatus) => {
                if("uptime" in fabricStatus && "status" in fabricStatus){
                    this.fabricService.fabric.uptime = fabricStatus['uptime'];
                    this.fabricService.fabric.status = fabricStatus['status'];
                    this.fabricRunning = (this.fabricService.fabric.status == 'running');
                }
            }
        );
    }
}
