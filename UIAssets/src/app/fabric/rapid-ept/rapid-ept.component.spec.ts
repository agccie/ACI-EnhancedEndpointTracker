import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { RapidEptComponent } from './rapid-ept.component';

describe('RapidEptComponent', () => {
  let component: RapidEptComponent;
  let fixture: ComponentFixture<RapidEptComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ RapidEptComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(RapidEptComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
