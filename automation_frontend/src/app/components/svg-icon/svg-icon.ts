import { Component, input } from '@angular/core';

export type IconName =
  | 'browser'
  | 'flows'
  | 'runs'
  | 'settings'
  | 'logo'
  | 'hamburger'
  | 'sun'
  | 'moon'
  | 'trash'
  | 'eye'
  | 'camera';

@Component({
  selector: 'app-svg-icon',
  standalone: true,
  templateUrl: './svg-icon.html',
  styleUrl: './svg-icon.css',
  host: { class: 'svg-icon-host' },
})
export class SvgIcon {
  readonly name = input.required<IconName>();
  /** Extra CSS class forwarded to the <svg> element */
  readonly cssClass = input<string>('');
}
