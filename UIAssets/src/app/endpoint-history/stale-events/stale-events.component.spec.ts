import {async, ComponentFixture, TestBed} from '@angular/core/testing';

import {StaleEventsComponent} from './stale-events.component';

describe('StaleEventsComponent', () => {
    let component: StaleEventsComponent;
    let fixture: ComponentFixture<StaleEventsComponent>;

    beforeEach(async(() => {
        TestBed.configureTestingModule({
            declarations: [StaleEventsComponent]
        })
            .compileComponents();
    }));

    beforeEach(() => {
        fixture = TestBed.createComponent(StaleEventsComponent);
        component = fixture.componentInstance;
        fixture.detectChanges();
    });

    it('should create', () => {
        expect(component).toBeTruthy();
    });
});
