import { Component, inject, input, output, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { InputDetectedData, InputValidation, InputValidationMode } from '../../types/websocket';
import { TooltipDirective } from '../../directives/tooltip/tooltip.directive';

export interface InputOverlayConfirmPayload {
  text: string;
  inputValidation: InputValidation | null;
}

@Component({
  selector: 'app-input-overlay',
  standalone: true,
  imports: [FormsModule, TooltipDirective],
  templateUrl: './input-overlay.html',
  styleUrl: './input-overlay.css',
})
export class InputOverlay {
  /** Data from INPUT_DETECTED event */
  readonly inputData = input.required<InputDetectedData>();
  /** Scaled pixel position (already converted to rendered image coords) */
  readonly posX = input<number>(0);
  readonly posY = input<number>(0);
  readonly enableValidation = input<boolean>(false);

  readonly confirm = output<InputOverlayConfirmPayload>();
  readonly cancel = output<void>();

  readonly inputValue = signal('');
  readonly validationError = signal<string | null>(null);
  readonly showValidationModal = signal(false);

  readonly required = signal(false);
  readonly validationDescription = signal('');
  readonly minLength = signal<number | null>(null);
  readonly maxLength = signal<number | null>(null);
  readonly selectedMode = signal<InputValidationMode | null>(null);
  readonly customRegex = signal('');
  readonly allowNegativeNumber = signal(false);

  readonly inputType = computed(() =>
    this.inputData().is_password ? 'password' : 'text'
  );

  readonly inputPlaceholder = computed(() =>
    this.inputData().placeholder || 'Type value and press OK or Enter'
  );

  readonly displayLabel = computed(() =>
    this.inputData().label || this.inputData().placeholder || 'Enter value'
  );

  ngOnInit(): void {
    const currentValue = this.inputData().current_value || '';
    const placeholder = this.inputData().placeholder || '';

    // If the detected value is just mirroring placeholder text, keep the input empty
    // and let the placeholder guide the user instead of treating it as typed content.
    this.inputValue.set(currentValue === placeholder ? '' : currentValue);
  }

  onOk(): void {
    this.validationError.set(null);
    const val = this.inputValue().trim();
    if (val || !this.inputData().is_password) {
      const inputValidation = this.buildValidationPayload();
      if (this.enableValidation() && this.selectedMode() === 'custom' && inputValidation?.customRegex) {
        try {
          new RegExp(inputValidation.customRegex);
        } catch {
          this.validationError.set('Custom regex is invalid.');
          return;
        }
      }
      this.confirm.emit({ text: this.inputValue(), inputValidation });
    }
  }

  onCancel(): void {
    this.cancel.emit();
  }

  openValidationModal(event?: Event): void {
    event?.stopPropagation();
    this.showValidationModal.set(true);
  }

  closeValidationModal(event?: Event): void {
    event?.stopPropagation();
    this.showValidationModal.set(false);
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter') { event.preventDefault(); this.onOk(); }
    if (event.key === 'Escape') { this.onCancel(); }
  }

  setMode(mode: InputValidationMode | null): void {
    this.selectedMode.set(mode);
    if (mode !== 'custom') {
      this.customRegex.set('');
    }
    if (mode !== 'numeric') {
      this.allowNegativeNumber.set(false);
    }
  }

  private buildValidationPayload(): InputValidation | null {
    if (!this.enableValidation()) {
      return null;
    }

    const payload: InputValidation = {
      required: this.required(),
      description: this.validationDescription().trim() || null,
      mode: this.selectedMode(),
      minLength: this.minLength(),
      maxLength: this.maxLength(),
      customRegex: this.customRegex().trim() || null,
      allowNegativeNumber: this.allowNegativeNumber(),
    };

    const hasRules = Boolean(
      payload.required ||
      payload.description ||
      payload.mode ||
      payload.minLength !== null ||
      payload.maxLength !== null ||
      payload.customRegex
    );

    return hasRules ? payload : null;
  }
}
