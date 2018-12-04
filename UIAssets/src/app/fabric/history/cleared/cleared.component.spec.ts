import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { ClearedComponent } from './cleared.component';

describe('ClearedComponent', () => {
  let component: ClearedComponent;
  let fixture: ComponentFixture<ClearedComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ ClearedComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(ClearedComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
