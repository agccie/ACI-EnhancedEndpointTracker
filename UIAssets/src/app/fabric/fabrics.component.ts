import {Component} from '@angular/core';
import {BackendService} from '../_service/backend.service';
import {ActivatedRoute, Router} from '@angular/router';
import {PreferencesService} from '../_service/preferences.service';
import {ModalService} from "../_service/modal.service";
import {QueryBuilderConfig} from "angular2-query-builder";
import {FormBuilder, FormControl} from "@angular/forms";


@Component({
    selector: 'app-fabrics',
    templateUrl: './fabrics.component.html',
    styleUrls: ['./fabrics.component.css']
})

export class FabricsComponent {
    endpointExpanded: boolean;
    configurationExpanded: boolean;
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

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, private activatedRoute: ActivatedRoute, public modalService: ModalService, private formBuilder: FormBuilder) {
        this.endpointExpanded = true;
        this.configurationExpanded = false;
        this.queryText = '';
    }

    ngOnInit(): void {
        this.activatedRoute.paramMap.subscribe(params => {
            this.fabricName = params.get('fabric');
            this.queryCtrl = this.formBuilder.control(this.query);
            this.currentConfig = this.config;
        });
    }

    onChange() {
        this.queryText = this.queryToText();
    }

    private valueToSQL(value) {
        switch (typeof value) {
            case 'string':
                return "'" + value + "'";
            case 'boolean':
                return value ? '1' : '0';
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
}
