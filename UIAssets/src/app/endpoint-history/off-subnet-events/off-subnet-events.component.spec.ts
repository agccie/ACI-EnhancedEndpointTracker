import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { OffSubnetEventsComponent } from './off-subnet-events.component';

describe('OffSubnetEventsComponent', () => {
  let component: OffSubnetEventsComponent;
  let fixture: ComponentFixture<OffSubnetEventsComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ OffSubnetEventsComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(OffSubnetEventsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
