import {async, ComponentFixture, TestBed} from '@angular/core/testing';

import {FabricsComponent} from './fabrics.component';

describe('FabricsComponent', () => {
    let component: FabricsComponent;
    let fixture: ComponentFixture<FabricsComponent>;

    beforeEach(async(() => {
        TestBed.configureTestingModule({
            declarations: [FabricsComponent]
        })
            .compileComponents();
    }));

    beforeEach(() => {
        fixture = TestBed.createComponent(FabricsComponent);
        component = fixture.componentInstance;
        fixture.detectChanges();
    });

    it('should create', () => {
        expect(component).toBeTruthy();
    });
});
