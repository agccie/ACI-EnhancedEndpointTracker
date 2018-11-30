import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { ClearedEptComponent } from './cleared-ept.component';

describe('ClearedEptComponent', () => {
  let component: ClearedEptComponent;
  let fixture: ComponentFixture<ClearedEptComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ ClearedEptComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(ClearedEptComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
