import { TestBed } from '@angular/core/testing';

import { WebsocketApi } from './websocket.api';

describe('WebsocketApi', () => {
  let service: WebsocketApi;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(WebsocketApi);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
