import { Component, EventEmitter, Input, OnChanges, OnDestroy, Output, SimpleChanges } from '@angular/core';

@Component({
  selector: 'app-run-result-popup',
  standalone: true,
  templateUrl: './run-result-popup.html',
  styleUrl: './run-result-popup.css',
})
export class RunResultPopup implements OnChanges, OnDestroy {
  @Input() visible = false;
  @Input() title = '';
  @Input() message = '';
  @Input() isHtml = false;
  @Input() variant: 'success' | 'error' = 'success';
  @Input() autoCloseMs = 2000;

  @Output() closed = new EventEmitter<void>();

  private _autoCloseTimer: ReturnType<typeof setTimeout> | null = null;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['visible'] || changes['autoCloseMs']) {
      this._restartAutoCloseTimer();
    }
  }

  ngOnDestroy(): void {
    this._clearAutoCloseTimer();
  }

  close(): void {
    this._clearAutoCloseTimer();
    this.closed.emit();
  }

  private _restartAutoCloseTimer(): void {
    this._clearAutoCloseTimer();
    if (!this.visible || this.autoCloseMs <= 0) return;
    this._autoCloseTimer = setTimeout(() => this.close(), this.autoCloseMs);
  }

  private _clearAutoCloseTimer(): void {
    if (this._autoCloseTimer) {
      clearTimeout(this._autoCloseTimer);
      this._autoCloseTimer = null;
    }
  }
}
