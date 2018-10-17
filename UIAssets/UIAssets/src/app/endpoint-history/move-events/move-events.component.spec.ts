import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { MoveEventsComponent } from './move-events.component';

describe('MoveEventsComponent', () => {
  let component: MoveEventsComponent;
  let fixture: ComponentFixture<MoveEventsComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ MoveEventsComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(MoveEventsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
