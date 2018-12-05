import {Component, OnInit, TemplateRef, ViewChild} from "@angular/core";
import {BackendService} from "../_service/backend.service";
import {PreferencesService} from "../_service/preferences.service";
import {Queue, QueueList} from "../_model/queue";
import {ActivatedRoute, Router} from "@angular/router";
import * as Highcharts from 'highcharts/highstock';
import {ModalService} from "../_service/modal.service";

@Component({
    templateUrl: './queue-detail.component.html',
    styleUrls: ['./queue-detail.component.css']
})

export class QueueDetailComponent implements OnInit {
    queues: any[];
    rows: any[];
    loading: boolean;
    pageNumber: number;
    pageSize: number;
    count: number;
    sorts = [{prop: 'dn', dir: 'asc'}];
    queue: Queue;
    dn: string;
    highcharts = Highcharts;
    chartConstructor = 'stockChart';
    chartOptions = {
        chart: {
            zoomType: 'x'
        },
        title: {
            text: 'Message rate'
        },
        legend: {
            enabled: true
        },
        xAxis: {
            gridLineWidth: 1,
            type: 'datetime',
            title: {
                text: 'Time'
            }
        },
        yAxis: {
            gridLineWidth: 1,
            title: {
                text: 'Message rate'
            }
        },
        plotOptions: {
            spline: {
                marker: {
                    enabled: true
                }
            }
        },
        series: [{
            name: 'RX',
            showInLegend: true,
            data: [],
            type: 'spline',
        }, {
            name: 'TX',
            showInLegend: true,
            data: [],
            type: 'spline',
        }]
    };
    chart: any;
    dropdownActive: boolean;
    currentGraph: string;
    dropDownValue: string;
    statsTypes: Map<string, {}>;
    @ViewChild('errorMsg') msgModal: TemplateRef<any>;

    constructor(public backendService: BackendService, private router: Router, private prefs: PreferencesService, private activatedRoute: ActivatedRoute,
                public modalService: ModalService) {
        this.rows = [];
        this.queues = [];
        this.pageSize = this.prefs.pageSize;
        this.pageNumber = 0;
        this.dropdownActive = false;
        this.dropDownValue = 'Select an option';
        this.statsTypes = new Map<string, {}>();
        this.statsTypes.set('1', {value: '1 minute', index: 'stats_1min'});
        this.statsTypes.set('2', {value: '5 minutes', index: 'stats_5min'});
        this.statsTypes.set('3', {value: '1 hour', index: 'stats_1hour'});
        this.statsTypes.set('4', {value: '1 day', index: 'stats_1day'});
        this.statsTypes.set('5', {value: '1 week', index: 'stats_1week'});
    }

    ngOnInit(): void {
        this.loading = true;
        this.activatedRoute.paramMap.subscribe(params => {
            this.dn = params.get('dn');
            if (this.dn != null) {
                this.backendService.getQueue(this.dn).subscribe((results: QueueList) => {
                    this.queue = results.objects[0]['ept.queue'];
                    this.loading = false;
                }, (err) => {
                    this.loading = false;
                    const msg = 'Failed to load queue! ' + err['error']['error'];
                    this.modalService.setAndOpenModal('error', 'Error', msg, this.msgModal);
                });
            }
        });
    }

    public onChartInstance(chart: any) {
        this.chart = chart;
        this.makeCharts();
    }

    private makeCharts(statsType = '1') {
        this.dropDownValue = this.statsTypes.get(statsType)['value'];
        const stats = this.queue[this.statsTypes.get(statsType)['index']];
        let rx_data = [];
        let tx_data = [];
        for (const stat of stats) {
            let timestamp = stat.timestamp * 1000;
            rx_data.unshift([timestamp, Math.floor(stat.rx_msg_rate)]);
            tx_data.unshift([timestamp, Math.floor(stat.tx_msg_rate)]);
        }
        this.chart.series[0].setData(rx_data);
        this.chart.series[1].setData(tx_data);
        this.chart.zoomOut()
    }
}
