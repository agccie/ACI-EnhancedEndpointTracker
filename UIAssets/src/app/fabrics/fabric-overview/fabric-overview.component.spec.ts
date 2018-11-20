import {async, ComponentFixture, TestBed} from '@angular/core/testing';

import {FabricOverviewComponent} from './fabric-overview.component';

describe('FabricOverviewComponent', () => {
    let component: FabricOverviewComponent;
    let fixture: ComponentFixture<FabricOverviewComponent>;

    beforeEach(async(() => {
        TestBed.configureTestingModule({
            declarations: [FabricOverviewComponent]
        })
            .compileComponents();
    }));

    beforeEach(() => {
        fixture = TestBed.createComponent(FabricOverviewComponent);
        component = fixture.componentInstance;
        fixture.detectChanges();
    });

    it('should create', () => {
        expect(component).toBeTruthy();
    });
});
