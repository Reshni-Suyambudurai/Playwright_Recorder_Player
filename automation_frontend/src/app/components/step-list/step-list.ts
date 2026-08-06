import { Component, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RecordingStep } from '../../types/websocket';
import { TabGroup } from '../../pages/runs/runs';
import { TooltipDirective } from '../../directives/tooltip/tooltip.directive';

@Component({
  selector: 'app-step-list',
  standalone: true,
  imports: [FormsModule, TooltipDirective],
  templateUrl: './step-list.html',
  styleUrl: './step-list.css',
})
export class StepList {
  readonly groups        = input.required<TabGroup[]>();
  readonly currentStepId = input<number | null>(null);
  readonly editValues    = input.required<Map<number, string>>();
  readonly validationErrors = input.required<Map<number, string>>();
  readonly shouldRunState = input.required<Map<number, boolean>>();
  readonly pauseState    = input.required<Map<number, boolean>>();

  readonly toggleShouldRun = output<{ stepId: number; current: boolean }>();
  readonly togglePause     = output<{ stepId: number; current: boolean }>();
  readonly editValue       = output<{ stepId: number; value: string }>();

  getShouldRun(step: RecordingStep): boolean {
    const m = this.shouldRunState();
    return m.has(step.id) ? (m.get(step.id) ?? true) : (step.shouldRun ?? true);
  }

  getPause(step: RecordingStep): boolean {
    const m = this.pauseState();
    return m.has(step.id) ? (m.get(step.id) ?? false) : (step.pause ?? false);
  }

  getEditValue(step: RecordingStep): string {
    const m = this.editValues();
    return m.has(step.id) ? (m.get(step.id) ?? '') : (step.text ?? '');
  }

  onToggleShouldRun(step: RecordingStep): void {
    this.toggleShouldRun.emit({ stepId: step.id, current: this.getShouldRun(step) });
  }

  onTogglePause(step: RecordingStep): void {
    this.togglePause.emit({ stepId: step.id, current: this.getPause(step) });
  }

  onEditInput(stepId: number, value: string): void {
    this.editValue.emit({ stepId, value });
  }

  getValidationDescription(step: RecordingStep): string | null {
    const description = step.inputValidation?.description?.trim();
    return description ? description : null;
  }

  getValidationError(step: RecordingStep): string | null {
    return this.validationErrors().get(step.id) ?? null;
  }
}
