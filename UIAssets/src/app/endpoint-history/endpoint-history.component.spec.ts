import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { EndpointHistoryComponent } from './endpoint-history.component';

describe('EndpointHistoryComponent', () => {
  let component: EndpointHistoryComponent;
  let fixture: ComponentFixture<EndpointHistoryComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ EndpointHistoryComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(EndpointHistoryComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
