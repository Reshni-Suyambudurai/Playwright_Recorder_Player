import { Component, inject, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RecordingsApi } from '../../services/recordings.api';
import { RecordingListItem, RecordingDetail, RecordingStep } from '../../types/websocket';
import { SvgIcon } from '../../components/svg-icon/svg-icon';
import { TooltipDirective } from '../../directives/tooltip/tooltip.directive';

export interface TabGroup {
  tabId: string;
  url: string;
  steps: RecordingStep[];
}

@Component({
  selector: 'app-runs',
  standalone: true,
  imports: [SvgIcon, FormsModule, TooltipDirective],
  templateUrl: './runs.html',
  styleUrl: './runs.css',
})
export class Runs implements OnInit {
  private api = inject(RecordingsApi);

  readonly recordings = signal<RecordingListItem[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly selectedId = signal<string>('');
  readonly detail = signal<RecordingDetail | null>(null);
  readonly detailLoading = signal(false);

  /** Locally edited text values keyed by step.id */
  readonly editValues = signal<Map<number, string>>(new Map());
  /** Locally toggled `shouldRun` state keyed by step.id */
  readonly shouldRunState = signal<Map<number, boolean>>(new Map());
  /** Locally toggled `pause` state keyed by step.id */
  readonly pauseState = signal<Map<number, boolean>>(new Map());

  readonly saving = signal(false);
  readonly saveError = signal<string | null>(null);
  readonly saveSuccess = signal(false);

  async ngOnInit(): Promise<void> {
    try {
      const list = await this.api.listRecordings();
      this.recordings.set(list);
    } catch (e: any) {
      this.error.set(e?.message ?? 'Failed to load recordings');
    } finally {
      this.loading.set(false);
    }
  }

  async onSelect(event: Event): Promise<void> {
    const id = (event.target as HTMLSelectElement).value;
    this.selectedId.set(id);
    this.detail.set(null);
    this.editValues.set(new Map());
    this.shouldRunState.set(new Map());
    this.pauseState.set(new Map());
    this.saveError.set(null);
    this.saveSuccess.set(false);
    if (!id) return;
    this.detailLoading.set(true);
    try {
      const d = await this.api.getRecording(id);
      this.detail.set(d);
    } catch {
      this.detail.set(null);
    } finally {
      this.detailLoading.set(false);
    }
  }

  selectedRecording(): RecordingListItem | undefined {
    return this.recordings().find(r => r.recordId === this.selectedId());
  }

  tabGroups(detail: RecordingDetail): TabGroup[] {
    return Object.entries(detail.steps).map(([tabId, groups]) => {
      const allSteps = (groups as RecordingStep[][]).flat();
      const nav = allSteps.find(s => s.type === 'NAVIGATE');
      const url = nav?.url ?? nav?.pageUrl ?? tabId;
      return { tabId, url, steps: allSteps };
    });
  }

  stepIcon(type: string): string {
    const icons: Record<string, string> = {
      NAVIGATE: '🌐', CLICK: '🖱️', TYPE: '⌨️',
      SCROLL: '↕️', KEY: '⌨️',
    };
    return icons[type] ?? '•';
  }

  stepLabel(step: RecordingStep): string {
    if (step.type === 'NAVIGATE') return step.url ?? step.pageUrl ?? '';
    if (step.type === 'TYPE') return step.text ? `"${step.text}"` : '';
    if (step.type === 'CLICK') return step.label ?? (step.coords ? `(${step.coords.x}, ${step.coords.y})` : '');
    if (step.type === 'SCROLL') return step.coords ? `(${step.coords.x}, ${step.coords.y})` : '';
    if (step.type === 'KEY') return step.text ?? '';
    return '';
  }

  formatDate(ts: number | null | undefined): string {
    if (!ts) return '';
    return new Date(ts).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  getEditValue(step: RecordingStep): string {
    const m = this.editValues();
    const raw = m.has(step.id) ? (m.get(step.id) ?? '') : (step.text ?? '');
    // If the stored value is a template placeholder like {{password}}, leave the input empty
    return /^\{\{.+\}\}$/.test(raw.trim()) ? '' : raw;
  }

  setEditValue(stepId: number, value: string): void {
    const m = new Map(this.editValues());
    m.set(stepId, value);
    this.editValues.set(m);
    this.saveSuccess.set(false);
  }

  getShouldRun(step: RecordingStep): boolean {
    const m = this.shouldRunState();
    return m.has(step.id) ? (m.get(step.id) ?? true) : (step.shouldRun ?? true);
  }

  toggleShouldRun(stepId: number, current: boolean): void {
    const m = new Map(this.shouldRunState());
    m.set(stepId, !current);
    this.shouldRunState.set(m);
  }

  getPause(step: RecordingStep): boolean {
    const m = this.pauseState();
    return m.has(step.id) ? (m.get(step.id) ?? false) : (step.pause ?? false);
  }

  togglePause(stepId: number, current: boolean): void {
    const m = new Map(this.pauseState());
    m.set(stepId, !current);
    this.pauseState.set(m);
  }

  hasEdits(): boolean {
    // Enable saving whenever a recording is loaded (user may have filled in values)
    if (this.detail()) return true;
    return this.editValues().size > 0;
  }

  async saveEdits(): Promise<void> {
    const current = this.detail();
    const id = this.selectedId();
    if (!current || !id || !this.hasEdits()) return;

    this.saving.set(true);
    this.saveError.set(null);
    this.saveSuccess.set(false);

    try {
      // Build updated steps with edited text values and shouldRun toggles merged in
      const updatedSteps: Record<string, RecordingStep[][]> = {};
      const edits = this.editValues();
      const shouldRunEdits = this.shouldRunState();
      const pauseEdits = this.pauseState();

      for (const [tabId, groups] of Object.entries(current.steps)) {
        updatedSteps[tabId] = (groups as RecordingStep[][]).map(group =>
          group.map(step => {
            let updated = step;
            if (shouldRunEdits.has(step.id)) {
              updated = { ...updated, shouldRun: shouldRunEdits.get(step.id)! };
            }
            if (pauseEdits.has(step.id)) {
              updated = { ...updated, pause: pauseEdits.get(step.id)! };
            }
            if (edits.has(step.id) && !step.isPassword) {
              updated = { ...updated, text: edits.get(step.id)! };
            }
            return updated;
          })
        );
      }

      const updatedRecording: RecordingDetail = {
        ...current,
        meta: { ...current.meta, updatedAt: Date.now() },
        steps: updatedSteps,
      };
      await this.api.saveRecording(id, updatedRecording);
      // Refresh local detail so saved values become canonical
      this.detail.set(updatedRecording);
      this.editValues.set(new Map());
      this.shouldRunState.set(new Map());
      this.pauseState.set(new Map());
      this.saveSuccess.set(true);
    } catch (e: any) {
      this.saveError.set(e?.message ?? 'Save failed');
    } finally {
      this.saving.set(false);
    }
  }
}
