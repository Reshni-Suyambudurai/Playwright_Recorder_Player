import {
  Directive,
  ElementRef,
  HostListener,
  inject,
  input,
  OnDestroy,
} from '@angular/core';

export type TooltipPosition = 'top' | 'right' | 'bottom' | 'left';

@Directive({
  selector: '[appTooltip]',
  standalone: true,
})
export class TooltipDirective implements OnDestroy {
  /** Tooltip text. Empty string disables the tooltip. */
  readonly appTooltip = input.required<string>();
  /** Where the tooltip appears relative to the host element. Default: 'right' */
  readonly tooltipPosition = input<TooltipPosition>('right');

  private el = inject(ElementRef<HTMLElement>);
  private tooltipEl: HTMLElement | null = null;

  @HostListener('mouseenter')
  onEnter(): void {
    const text = this.appTooltip();
    if (!text) return;
    this.show(text);
  }

  @HostListener('mouseleave')
  onLeave(): void {
    this.hide();
  }

  @HostListener('click')
  onClick(): void {
    this.hide();
  }

  ngOnDestroy(): void {
    this.hide();
  }

  private show(text: string): void {
    this.hide(); // prevent duplicates

    const tip = document.createElement('div');
    tip.className = `app-tooltip app-tooltip--${this.tooltipPosition()}`;
    tip.textContent = text;
    document.body.appendChild(tip);
    this.tooltipEl = tip;

    // Position after appending so we can measure it
    requestAnimationFrame(() => {
      if (!this.tooltipEl) return;
      const hostRect = this.el.nativeElement.getBoundingClientRect();
      const tipRect  = this.tooltipEl.getBoundingClientRect();
      const gap = 8;
      let top = 0;
      let left = 0;

      switch (this.tooltipPosition()) {
        case 'right':
          top  = hostRect.top  + hostRect.height / 2 - tipRect.height / 2 + window.scrollY;
          left = hostRect.right + gap + window.scrollX;
          break;
        case 'left':
          top  = hostRect.top  + hostRect.height / 2 - tipRect.height / 2 + window.scrollY;
          left = hostRect.left - tipRect.width - gap + window.scrollX;
          break;
        case 'top':
          top  = hostRect.top  - tipRect.height - gap + window.scrollY;
          left = hostRect.left + hostRect.width / 2 - tipRect.width / 2 + window.scrollX;
          break;
        case 'bottom':
          top  = hostRect.bottom + gap + window.scrollY;
          left = hostRect.left + hostRect.width / 2 - tipRect.width / 2 + window.scrollX;
          break;
      }

      this.tooltipEl.style.top  = `${top}px`;
      this.tooltipEl.style.left = `${left}px`;
      this.tooltipEl.classList.add('app-tooltip--visible');
    });
  }

  private hide(): void {
    if (this.tooltipEl) {
      this.tooltipEl.remove();
      this.tooltipEl = null;
    }
  }
}
