import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Runs } from './runs';

describe('Runs', () => {
  let component: Runs;
  let fixture: ComponentFixture<Runs>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Runs],
    }).compileComponents();

    fixture = TestBed.createComponent(Runs);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
