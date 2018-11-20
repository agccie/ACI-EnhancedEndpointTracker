import {async, ComponentFixture, TestBed} from '@angular/core/testing';

import {OffsubnetEptComponent} from './offsubnet-ept.component';

describe('OffsubnetEptComponent', () => {
    let component: OffsubnetEptComponent;
    let fixture: ComponentFixture<OffsubnetEptComponent>;

    beforeEach(async(() => {
        TestBed.configureTestingModule({
            declarations: [OffsubnetEptComponent]
        })
            .compileComponents();
    }));

    beforeEach(() => {
        fixture = TestBed.createComponent(OffsubnetEptComponent);
        component = fixture.componentInstance;
        fixture.detectChanges();
    });

    it('should create', () => {
        expect(component).toBeTruthy();
    });
});
