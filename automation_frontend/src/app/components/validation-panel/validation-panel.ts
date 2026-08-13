import { Component, computed, inject } from '@angular/core';
import { ValidationStateApi } from '../../services/validation-state.api';
import { ValidationDiscoveryData, ValidationGroup, ValidationCatalogOption } from '../../types/websocket';

@Component({
  selector: 'app-validation-panel',
  standalone: true,
  templateUrl: './validation-panel.html',
  styleUrl: './validation-panel.css',
})
export class ValidationPanel {
  private validationState = inject(ValidationStateApi);
  openGroupKey: string | null = null;

  readonly context = this.validationState.activeContext;
  readonly hasContext = this.validationState.hasContext;
  readonly currentValidation = computed(() => this.context());

  toggleOption(groupKey: string, optionKey: string): void {
    this.validationState.toggleOption(groupKey, optionKey);
  }

  isSelected(groupKey: string, optionKey: string): boolean {
    return this.validationState.isSelected(groupKey, optionKey);
  }

  isDropdownValidation(validation: ValidationDiscoveryData): boolean {
    const role = validation?.elementSnapshot?.ariaRole?.toLowerCase?.() ?? '';
    const keys: string[] = validation?.matchedCatalogKeys ?? [];
    return keys.includes('dropdown') || role === 'combobox' || role === 'listbox';
  }

  getDropdownOptions(validation: ValidationDiscoveryData): string[] {
    return validation?.elementSnapshot?.dropdownOptions ?? [];
  }

  getDropdownOptionCount(validation: ValidationDiscoveryData): number {
    const explicitCount = validation?.elementSnapshot?.optionCount;
    if (typeof explicitCount === 'number') return explicitCount;
    return this.getDropdownOptions(validation).length;
  }

  shouldRenderOption(validation: ValidationDiscoveryData, group: ValidationGroup, option: ValidationCatalogOption): boolean {
    if (!this.isDropdownValidation(validation)) return true;
    if (group.key !== 'selection') return true;
    return option.key === 'option_count';
  }

  optionValueText(validation: ValidationDiscoveryData, group: ValidationGroup, option: ValidationCatalogOption): string | null {
    const snapshot = validation.elementSnapshot;
    const key = option.key;

    if (this.isDropdownValidation(validation)) {
      if (group.key === 'selection' && key === 'option_count') {
        return String(this.getDropdownOptionCount(validation));
      }
    }

    if (validation.matchedCatalogKeys.includes('button')) {
      if (key === 'text') return snapshot.textContent || snapshot.currentValue || snapshot.value || 'N/A';
      if (key === 'color') return snapshot.computedStyle?.color || 'N/A';
      if (key === 'width') return this._toPx(snapshot.boundingRect?.width);
      if (key === 'height') return this._toPx(snapshot.boundingRect?.height);
    }

    if (validation.matchedCatalogKeys.includes('input')) {
      if (key === 'equals_value' || key === 'contains_value' || key === 'starts_with' || key === 'ends_with' || key === 'empty') {
        return snapshot.currentValue || snapshot.value || '';
      }
      if (key === 'placeholder') return snapshot.placeholder || 'N/A';
      if (key === 'border_color') return snapshot.computedStyle?.borderColor || 'N/A';
      if (key === 'background_color') return snapshot.computedStyle?.backgroundColor || 'N/A';
      if (key === 'css_class') return snapshot.className || 'N/A';
    }

    return option.description?.trim() || null;
  }

  private _toPx(value: number | undefined): string {
    if (typeof value !== 'number') return 'N/A';
    return `${Math.round(value)}px`;
  }

  getStepLabel(stepId?: number, stepType?: string): string {
    return this.validationState.getStepLabel(stepId, stepType);
  }

  getActionType(validation: ValidationDiscoveryData): string {
    return validation.stepType || 'UNKNOWN';
  }

  getValidationType(validation: ValidationDiscoveryData): string {
    if (validation.elementCategory?.trim()) {
      return validation.elementCategory;
    }

    const fallback = validation.matchedCatalogKeys?.[0] ?? 'unknown';
    return fallback.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
  }

  isGroupOpen(groupKey: string): boolean {
    return this.openGroupKey === groupKey;
  }

  onGroupToggle(groupKey: string, event: Event): void {
    const detailsElement = event.currentTarget as HTMLDetailsElement | null;
    if (!detailsElement) {
      return;
    }

    this.openGroupKey = detailsElement.open ? groupKey : null;
  }
}
