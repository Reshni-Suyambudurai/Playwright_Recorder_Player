import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RecordingModal } from './recording-modal';

describe('RecordingModal', () => {
  let component: RecordingModal;
  let fixture: ComponentFixture<RecordingModal>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RecordingModal],
    }).compileComponents();

    fixture = TestBed.createComponent(RecordingModal);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
