import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

export interface SaveRecordingDialogData {
  title: string;
  intent: string;
  description: string;
  saveOption: 'cancel' | 'save_as_new' | 'save_delete_old';
}

@Component({
  selector: 'app-pause-recording-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './pause-recording-dialog.html',
  styleUrl: './pause-recording-dialog.css',
})
export class PauseRecordingDialog implements OnChanges {
  @Input() isVisible = false;
  @Input() pauseStepCount = 0;
  @Input() recordingTitle = '';
  @Output() onSave = new EventEmitter<SaveRecordingDialogData>();
  @Output() onCancel = new EventEmitter<void>();

  title = '';
  intent = '';
  description = '';
  isSaving = false;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['isVisible']?.currentValue === true) {
      this.title = `${this.recordingTitle.trim()} V2`.trim();
      this.intent = '';
      this.description = '';
    }
  }

  handleSave(saveOption: 'save_as_new' | 'save_delete_old'): void {
    if (!this.title.trim()) return;

    this.isSaving = true;

    this.onSave.emit({
      title: this.title.trim(),
      intent: this.intent.trim(),
      description: this.description.trim(),
      saveOption,
    });

    setTimeout(() => {
      this.isSaving = false;
    }, 500);
  }

  handleCancel(): void {
    this.onCancel.emit();
  }
}
