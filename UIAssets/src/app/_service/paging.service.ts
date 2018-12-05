import {Injectable} from '@angular/core';

@Injectable({
    providedIn: 'root'
})

export class PagingService {
    count: number;
    pageOffset: number;
    pageSize: number;
    sorts: any;
    fabricName: string;

    constructor() {
        this.count = 0;
        this.pageOffset = 0;
        this.sorts = {};
    }
}
