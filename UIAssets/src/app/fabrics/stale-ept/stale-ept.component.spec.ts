import { async, ComponentFixture, TestBed } from '@angular/core/testing';

import { StaleEptComponent } from './stale-ept.component';

describe('StaleEptComponent', () => {
  let component: StaleEptComponent;
  let fixture: ComponentFixture<StaleEptComponent>;

  beforeEach(async(() => {
    TestBed.configureTestingModule({
      declarations: [ StaleEptComponent ]
    })
    .compileComponents();
  }));

  beforeEach(() => {
    fixture = TestBed.createComponent(StaleEptComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
