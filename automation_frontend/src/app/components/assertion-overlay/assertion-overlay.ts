import { Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';

/**
 * Assertion overlay component - displays assertion data at hover position.
 * Read-only display of mode-specific discovered element data.
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
  readonly mode = input<'visibility' | 'text' | 'value' | null>(null);
  readonly data = input<any>(null);
  readonly posX = input<number>(0);
  readonly posY = input<number>(0);

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
    };
    return labels[key] || key;
  }

  formatValue(value: any): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? '✓' : '✗';
    if (Array.isArray(value)) return `[${value.length}]`;
    if (typeof value === 'object') return JSON.stringify(value);
    if (typeof value === 'string') return value.length > 50 ? value.substring(0, 50) + '…' : value;
    return String(value);
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
      default:
        return [];
    }
  }
}
