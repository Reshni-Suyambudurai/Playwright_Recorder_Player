import { Component, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-recording-modal',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './recording-modal.html',
  styleUrl: './recording-modal.css',
})
export class RecordingModal {
  readonly confirm = output<string>();  // emits the recording name
  readonly cancel = output<void>();

  readonly recordingName = signal('');
  readonly nameError = signal('');

  onConfirm(): void {
    const name = this.recordingName().trim();
    if (!name) {
      this.nameError.set('Recording name is required.');
      return;
    }
    this.nameError.set('');
    this.confirm.emit(name);
  }

  onCancel(): void {
    this.reset();
    this.cancel.emit();
  }

  reset(): void {
    this.recordingName.set('');
    this.nameError.set('');
  }
}
