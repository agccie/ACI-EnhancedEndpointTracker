import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { LocalLearnsComponent } from './local-learns.component';

describe('LocalLearnsComponent', () => {
  let component: LocalLearnsComponent;
  let fixture: ComponentFixture<LocalLearnsComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ LocalLearnsComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(LocalLearnsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
