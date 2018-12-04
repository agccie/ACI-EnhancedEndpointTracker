import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { RapidComponent } from './rapid.component';

describe('RapidComponent', () => {
  let component: RapidComponent;
  let fixture: ComponentFixture<RapidComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ RapidComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(RapidComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
