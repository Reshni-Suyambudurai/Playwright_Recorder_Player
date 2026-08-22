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

  /** Synthetic group key the dropdown-options checklist is stored under in ValidationStateApi. */
  readonly DROPDOWN_GROUP_KEY = 'dropdown-options';

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

  /** Stable per-position key for a dropdown option — option text alone isn't guaranteed unique. */
  getDropdownOptionKey(index: number): string {
    return `opt-${index}`;
  }

  areAllDropdownOptionsSelected(validation: ValidationDiscoveryData): boolean {
    const options = this.getDropdownOptions(validation);
    return options.length > 0 && options.every((_, i) =>
      this.isSelected(this.DROPDOWN_GROUP_KEY, this.getDropdownOptionKey(i))
    );
  }

  isAnyDropdownOptionSelected(validation: ValidationDiscoveryData): boolean {
    return this.getDropdownOptions(validation).some((_, i) =>
      this.isSelected(this.DROPDOWN_GROUP_KEY, this.getDropdownOptionKey(i))
    );
  }

  toggleAllDropdownOptions(validation: ValidationDiscoveryData): void {
    const keys = this.getDropdownOptions(validation).map((_, i) => this.getDropdownOptionKey(i));
    const nextSelected = !this.areAllDropdownOptionsSelected(validation);
    this.validationState.setGroupOptionsSelected(this.DROPDOWN_GROUP_KEY, keys, nextSelected);
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

  /**
   * Single-select accordion toggle, driven entirely by openGroupKey — the sole source of
   * truth for which group is open (see [open]="isGroupOpen(...)" in the template).
   * The native click is prevented so the browser never toggles <details> on its own; without
   * that, its own toggle and this state update race, which is what caused the "click once to
   * close the old group, click again to actually open the new one" bug.
   */
  onGroupSummaryClick(groupKey: string, event: Event): void {
    event.preventDefault();
    const opening = this.openGroupKey !== groupKey;
    this.openGroupKey = opening ? groupKey : null;

    if (opening) {
      // The clicked <details> hasn't expanded yet on this tick — wait a frame so its full
      // height is in the DOM, then bring it fully into view. Without this, opening the last
      // group in the scroll container leaves its bottom content below the visible area.
      const summary = event.currentTarget as HTMLElement | null;
      requestAnimationFrame(() => {
        summary?.closest('details')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      });
    }
  }
}
