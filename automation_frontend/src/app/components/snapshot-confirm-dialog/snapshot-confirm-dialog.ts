import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-snapshot-confirm-dialog',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './snapshot-confirm-dialog.html',
  styleUrl: './snapshot-confirm-dialog.css',
})
export class SnapshotConfirmDialog {
  @Input() isOpen = false;
  @Input() message = 'Capture full-page accessibility snapshot?';
  @Input() confirmLabel = 'Capture';
  @Input() cancelLabel = 'Cancel';

  @Output() confirm = new EventEmitter<void>();
  @Output() cancel = new EventEmitter<void>();

  onConfirm(): void {
    this.confirm.emit();
  }

  onCancel(): void {
    this.cancel.emit();
  }
}
