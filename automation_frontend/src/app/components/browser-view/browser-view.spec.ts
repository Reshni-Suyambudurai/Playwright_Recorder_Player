import { ComponentFixture, TestBed } from '@angular/core/testing';
import { BrowserView } from './browser-view';
import { WebsocketApi } from '../../services/websocket.api';
import { EMPTY } from 'rxjs';

describe('BrowserView', () => {
  let component: BrowserView;
  let fixture: ComponentFixture<BrowserView>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [BrowserView],
      providers: [
        { provide: WebsocketApi, useValue: { frame$: EMPTY, sendClickAction: () => {} } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(BrowserView);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
