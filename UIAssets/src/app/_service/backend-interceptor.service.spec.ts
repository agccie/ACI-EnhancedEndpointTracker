import { TestBed, inject } from '@angular/core/testing';

import { BackendInterceptorService } from './backend-interceptor.service';

describe('BackendInterceptorService', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [BackendInterceptorService]
    });
  });

  it('should be created', inject([BackendInterceptorService], (service: BackendInterceptorService) => {
    expect(service).toBeTruthy();
  }));
});
