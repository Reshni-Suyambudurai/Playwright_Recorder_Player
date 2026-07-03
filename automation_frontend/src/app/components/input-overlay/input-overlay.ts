import { Component, inject, input, output, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { InputDetectedData } from '../../types/websocket';

@Component({
  selector: 'app-input-overlay',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './input-overlay.html',
  styleUrl: './input-overlay.css',
})
export class InputOverlay {
  /** Data from INPUT_DETECTED event */
  readonly inputData = input.required<InputDetectedData>();
  /** Scaled pixel position (already converted to rendered image coords) */
  readonly posX = input<number>(0);
  readonly posY = input<number>(0);

  readonly confirm = output<string>();  // emits the entered text
  readonly cancel = output<void>();

  readonly inputValue = signal('');

  readonly inputType = computed(() =>
    this.inputData().is_password ? 'password' : 'text'
  );

  readonly displayLabel = computed(() =>
    this.inputData().label || this.inputData().placeholder || 'Enter value'
  );

  ngOnInit(): void {
    // Pre-fill with current page value if any
    this.inputValue.set(this.inputData().current_value || '');
  }

  onOk(): void {
    const val = this.inputValue().trim();
    if (val || !this.inputData().is_password) {
      this.confirm.emit(this.inputValue());
    }
  }

  onCancel(): void {
    this.cancel.emit();
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter') { event.preventDefault(); this.onOk(); }
    if (event.key === 'Escape') { this.onCancel(); }
  }
}
