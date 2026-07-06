import { Component, inject, signal, OnInit } from '@angular/core';
import { RecordingsApi } from '../../services/recordings.api';
import { RecordingListItem, RecordingDetail, RecordingStep } from '../../types/websocket';
import { SvgIcon } from '../../components/svg-icon/svg-icon';

/** Flat step group by URL for the detail panel */
export interface TabGroup {
  tabId: string;
  url: string;
  steps: RecordingStep[];
}

/** Step types we consider "important" enough to show in the summary panel */
const KEY_TYPES = new Set(['NAVIGATE', 'CLICK', 'TYPE', 'KEY']);

@Component({
  selector: 'app-flows',
  standalone: true,
  imports: [SvgIcon],
  templateUrl: './flows.html',
  styleUrl: './flows.css',
})
export class Flows implements OnInit {
  private api = inject(RecordingsApi);

  readonly recordings = signal<RecordingListItem[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly deletingId = signal<string | null>(null);
  readonly pendingDeleteId = signal<string | null>(null);

  readonly selectedRecording = signal<RecordingListItem | null>(null);
  readonly detail = signal<RecordingDetail | null>(null);
  readonly detailLoading = signal(false);

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

  async onCardClick(rec: RecordingListItem): Promise<void> {
    this.selectedRecording.set(rec);
    this.detail.set(null);
    this.detailLoading.set(true);
    try {
      const d = await this.api.getRecording(rec.recordId);
      this.detail.set(d);
    } catch {
      this.detail.set(null);
    } finally {
      this.detailLoading.set(false);
    }
  }

  closeDetail(): void {
    this.selectedRecording.set(null);
    this.detail.set(null);
  }

  async onDeleteClick(event: MouseEvent, rec: RecordingListItem): Promise<void> {
    event.stopPropagation();
    this.pendingDeleteId.set(rec.recordId);
  }

  cancelDelete(): void {
    this.pendingDeleteId.set(null);
  }

  async confirmDelete(): Promise<void> {
    const id = this.pendingDeleteId();
    if (!id || this.deletingId()) return;
    this.deletingId.set(id);
    try {
      await this.api.deleteRecording(id);
      this.recordings.update(list => list.filter(r => r.recordId !== id));
      if (this.selectedRecording()?.recordId === id) {
        this.closeDetail();
      }
      this.pendingDeleteId.set(null);
    } catch (e: any) {
      this.error.set(e?.message ?? 'Delete failed');
    } finally {
      this.deletingId.set(null);
    }
  }

  /** Group steps by tab, using the first NAVIGATE URL as the section header */
  tabGroups(detail: RecordingDetail): TabGroup[] {
    return Object.entries(detail.steps).map(([tabId, groups]) => {
      const allSteps = groups.flat();
      const navigateStep = allSteps.find(s => s.type === 'NAVIGATE');
      const url = navigateStep?.url ?? navigateStep?.pageUrl ?? tabId;
      return { tabId, url, steps: allSteps };
    });
  }

  /** Total steps across all tabs */
  totalKeySteps(detail: RecordingDetail): number {
    return this.tabGroups(detail).reduce((n, g) => n + g.steps.length, 0);
  }

  stepIcon(type: string): string {
    const map: Record<string, string> = {
      NAVIGATE: '🌐', CLICK: '🖱️', TYPE: '⌨️', KEY: '↵', SCROLL: '↕️',
    };
    return map[type] ?? '•';
  }

  stepLabel(step: RecordingStep): string {
    if (step.type === 'NAVIGATE') return step.url ?? step.pageUrl ?? '';
    if (step.type === 'TYPE') return (step.label ?? step.tag ?? 'input') + ': ' + (step.text ?? '');
    if (step.type === 'CLICK') return step.label ?? step.tag ?? 'element';
    if (step.type === 'KEY') return 'Key: ' + (step.text ?? '');
    return step.pageUrl ?? '';
  }

  formatDate(ms: number | null): string {
    if (!ms) return '';
    return new Date(ms).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  formatDateTime(ms: number | null): string {
    if (!ms) return '';
    return new Date(ms).toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }
}

