import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';

/**
 * Assertion overlay component - displays assertion data at hover position.
 * Supports multiple modes:
 * - visibility, text, value: read-only hover tooltips
 * - snapshot: interactive preview with Cancel/Save buttons
 * Positioned absolutely at (posX, posY) relative to the browser view container.
 */
@Component({
  selector: 'app-assertion-overlay',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './assertion-overlay.html',
  styleUrl: './assertion-overlay.css',
})
export class AssertionOverlay {
  readonly mode = input<'visibility' | 'text' | 'value' | 'snapshot' | null>(null);
  readonly data = input<any>(null);
  readonly posX = input<number>(0);
  readonly posY = input<number>(0);

  // Snapshot mode outputs
  readonly saved = output<void>();
  readonly cancelled = output<void>();

  onSaveAssertion(): void {
    this.saved.emit();
  }

  onCancelAssertion(): void {
    this.cancelled.emit();
  }

  isArray(value: any): boolean {
    return Array.isArray(value);
  }

  getFieldLabel(key: string): string {
    const labels: Record<string, string> = {
      visible: 'Visible',
      display: 'Display',
      opacity: 'Opacity',
      text: 'Text',
      wordCount: 'Words',
      charCount: 'Chars',
      accessibleName: 'Aria Name',
      value: 'Value',
      type: 'Type',
      dropdownOptions: 'Options',
      optionCount: 'Count',
      selector: 'Selector',
      label: 'Selected',
      ariaSnapshot: 'ARIA Snapshot',
    };
    return labels[key] || key;
  }

  formatValue(value: any): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? '✓' : '✗';
    if (Array.isArray(value)) return `[${value.length}]`;
    if (typeof value === 'object') return JSON.stringify(value);
    // Don't truncate ARIA snapshot text - it's displayed in pre tag
    if (typeof value === 'string') return value;
    return String(value);
  }

  isAriaSnapshot(key: string): boolean {
    return key === 'ariaSnapshot';
  }

  getVisibleFields(): string[] {
    const data = this.data();
    if (!data) return [];

    switch (this.mode()) {
      case 'visibility':
        return ['visible', 'display', 'opacity'].filter(k => k in data);
      case 'text':
        return ['text', 'wordCount', 'charCount', 'accessibleName'].filter(k => k in data);
      case 'value':
        return ['value', 'type', 'optionCount'].filter(k => k in data);
      case 'snapshot':
        return ['label', 'ariaSnapshot'].filter(k => k in data);
      default:
        return [];
    }
  }
}
