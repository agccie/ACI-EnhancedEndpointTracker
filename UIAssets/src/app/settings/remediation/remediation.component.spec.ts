import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { RemediationComponent } from './remediation.component';

describe('RemediationComponent', () => {
  let component: RemediationComponent;
  let fixture: ComponentFixture<RemediationComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ RemediationComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(RemediationComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
