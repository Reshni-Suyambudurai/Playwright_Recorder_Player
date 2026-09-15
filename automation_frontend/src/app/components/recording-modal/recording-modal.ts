import { Component, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { StartRecordingData } from '../../types/websocket';

@Component({
  selector: 'app-recording-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './recording-modal.html',
  styleUrl: './recording-modal.css',
})
export class RecordingModal {
  readonly confirm = output<StartRecordingData>();
  readonly cancel = output<void>();

  readonly recordingName = signal('');
  readonly description = signal('');
  readonly intent = signal('');
  readonly nameError = signal('');

  onConfirm(): void {
    const name = this.recordingName().trim();
    if (!name) {
      this.nameError.set('Recording name is required.');
      return;
    }
    this.nameError.set('');
    this.confirm.emit({
      url: '',                          // filled by browser.ts
      recording_name: name,
      description: this.description().trim() || undefined,
      intent: this.intent().trim() || undefined,
    });
  }

  onCancel(): void {
    this.reset();
    this.cancel.emit();
  }

  reset(): void {
    this.recordingName.set('');
    this.description.set('');
    this.intent.set('');
    this.nameError.set('');
  }
}
