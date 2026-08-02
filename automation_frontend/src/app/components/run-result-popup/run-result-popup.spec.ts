import { ComponentFixture, TestBed } from '@angular/core/testing';

import { RunResultPopup } from './run-result-popup';

describe('RunResultPopup', () => {
  let component: RunResultPopup;
  let fixture: ComponentFixture<RunResultPopup>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RunResultPopup],
    }).compileComponents();

    fixture = TestBed.createComponent(RunResultPopup);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
