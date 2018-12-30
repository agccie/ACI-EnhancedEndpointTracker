import {Component, OnDestroy, OnInit, ViewEncapsulation, ViewChild} from '@angular/core';
import {BackendService} from '../_service/backend.service';
import {ActivatedRoute, Router} from '@angular/router';
import {PreferencesService} from '../_service/preferences.service';
import {ModalService} from "../_service/modal.service";
import {QueryBuilderConfig} from "angular2-query-builder";
import {FormBuilder, FormControl} from "@angular/forms";
import {concat, Observable, of, Subject} from "rxjs";
import {catchError, debounceTime, distinctUntilChanged, switchMap, tap} from "rxjs/operators";
import {NgSelectComponent} from '@ng-select/ng-select';

@Component({
    encapsulation: ViewEncapsulation.None,
    selector: 'app-fabrics',
    templateUrl: './fabrics.component.html',
    styleUrls: ['./fabrics.component.css']
})

export class FabricsComponent implements OnInit, OnDestroy {
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


    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, private activatedRoute: ActivatedRoute, public modalService: ModalService, private formBuilder: FormBuilder) {
        this.queryText = '';
    }

    ngOnInit(): void {
        localStorage.setItem('menuVisible', 'true');
        this.activatedRoute.paramMap.subscribe(params => {
            this.fabricName = params.get('fabric');
            this.queryCtrl = this.formBuilder.control(this.query);
            this.currentConfig = this.config;
        });
        this.searchEndpoint();
    }

    ngOnDestroy(): void {
        localStorage.setItem('menuVisible', 'false');
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
        if(endpoint && 'ept.endpoint' in endpoint && "vnid" in endpoint['ept.endpoint'] && endpoint['ept.endpoint'].vnid>0){
            const addr = endpoint['ept.endpoint'].addr;
            const vnid = endpoint['ept.endpoint'].vnid;
            const fabric = endpoint['ept.endpoint'].fabric;
            this.router.navigate(['/fabric', fabric, 'history', vnid, addr]);
        } else {
            //TODO - need to trigger clear of all text after selected
            //this.ngSelect...
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
                if("objects" in data && "count" in data){
                    this.endpointList = data["objects"];
                    // add dummy shim entry at index 0 
                    this.endpointList.unshift("");
                    this.endpointMatchCount = data["count"];
                }
            }
        );
    }


}
