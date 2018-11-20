import {async, ComponentFixture, TestBed} from '@angular/core/testing';

import {PerNodeHistoryComponent} from './per-node-history.component';

describe('PerNodeHistoryComponent', () => {
    let component: PerNodeHistoryComponent;
    let fixture: ComponentFixture<PerNodeHistoryComponent>;

    beforeEach(async(() => {
        TestBed.configureTestingModule({
            declarations: [PerNodeHistoryComponent]
        })
            .compileComponents();
    }));

    beforeEach(() => {
        fixture = TestBed.createComponent(PerNodeHistoryComponent);
        component = fixture.componentInstance;
        fixture.detectChanges();
    });

    it('should create', () => {
        expect(component).toBeTruthy();
    });
});
