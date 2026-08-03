import { Component, computed, inject, effect, ViewChild, ElementRef } from '@angular/core';
import { ValidationStateApi } from '../../services/validation-state.api';

@Component({
  selector: 'app-validation-panel',
  standalone: true,
  templateUrl: './validation-panel.html',
  styleUrl: './validation-panel.css',
})
export class ValidationPanel {
  private validationState = inject(ValidationStateApi);
  private previousHistoryCount = 0;

  @ViewChild('historyList')
  historyListRef?: ElementRef<HTMLDivElement>;

  // Publicly expose state for template
  readonly context = this.validationState.activeContext;
  readonly hasContext = this.validationState.hasContext;
  readonly selectedLabels = computed(() => this.validationState.selectedLabels());
  
  // History and accordion signals - publicly accessible in template
  readonly validationHistory = this.validationState.validationHistory;
  readonly displayedHistory = computed(() =>
    this.validationHistory().filter((entry) => entry.stepId !== undefined && !!entry.stepType),
  );
  readonly expandedStepId = this.validationState.expandedStepId;
  readonly currentStepId = this.validationState.currentStepId;

  constructor() {
    // Auto-scroll only when a new history item is appended.
    effect(() => {
      const historyCount = this.displayedHistory().length;
      const didGrow = historyCount > this.previousHistoryCount;
      this.previousHistoryCount = historyCount;

      if (!didGrow) {
        return;
      }

      setTimeout(() => {
        const listElement = this.historyListRef?.nativeElement;
        if (listElement) {
          listElement.scrollTop = listElement.scrollHeight;
        }
      }, 0);
    });
  }

  toggleOption(groupKey: string, optionKey: string): void {
    this.validationState.toggleOption(groupKey, optionKey);
  }

  isSelected(groupKey: string, optionKey: string): boolean {
    return this.validationState.isSelected(groupKey, optionKey);
  }
  
  // Get formatted step label (e.g., "1: CLICK")
  getStepLabel(stepId?: number, stepType?: string): string {
    return this.validationState.getStepLabel(stepId, stepType);
  }

  // Handle accordion toggle
  onToggleAccordion(stepId: number | null | undefined, event: Event): void {
    const detailsElement = event.currentTarget as HTMLDetailsElement | null;
    const sourceElement = event.target as HTMLElement | null;

    // Ignore nested <details> toggles bubbling from validation groups.
    if (!detailsElement || sourceElement !== detailsElement || stepId === undefined || stepId === null) {
      return;
    }

    this.validationState.setExpandedStep(detailsElement.open ? stepId : null);
  }
}
