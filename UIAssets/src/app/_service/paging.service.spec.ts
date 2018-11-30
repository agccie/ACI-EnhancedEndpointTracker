import { TestBed } from '@angular/core/testing';

import { PagingService } from './paging.service';

describe('PagingService', () => {
  beforeEach(() => TestBed.configureTestingModule({}));

  it('should be created', () => {
    const service: PagingService = TestBed.get(PagingService);
    expect(service).toBeTruthy();
  });
});
