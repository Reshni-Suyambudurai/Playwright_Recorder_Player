import { Component, computed, inject } from '@angular/core';
import { ValidationStateApi } from '../../services/validation-state.api';

@Component({
  selector: 'app-validation-panel',
  standalone: true,
  templateUrl: './validation-panel.html',
  styleUrl: './validation-panel.css',
})
export class ValidationPanel {
  private validationState = inject(ValidationStateApi);

  readonly context = this.validationState.activeContext;
  readonly hasContext = this.validationState.hasContext;
  readonly selectedLabels = computed(() => this.validationState.selectedLabels());

  toggleOption(groupKey: string, optionKey: string): void {
    this.validationState.toggleOption(groupKey, optionKey);
  }

  isSelected(groupKey: string, optionKey: string): boolean {
    return this.validationState.isSelected(groupKey, optionKey);
  }

  elementSummary(): string {
    const context = this.context();
    if (!context) return '';

    const snapshot = context.elementSnapshot;
    return [snapshot.tagName, snapshot.id ? `#${snapshot.id}` : '', snapshot.name ? `name=${snapshot.name}` : '', snapshot.ariaLabel ?? snapshot.placeholder ?? snapshot.textContent ?? '']
      .filter(Boolean)
      .join(' • ');
  }
}
