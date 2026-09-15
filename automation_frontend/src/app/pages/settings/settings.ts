import { Component } from '@angular/core';

@Component({
  selector: 'app-settings',
  standalone: true,
  template: `
    <div class="page-placeholder">
      <h2>Settings</h2>
      <p>Application settings and configuration will appear here.</p>
    </div>
  `,
  styles: [`
    .page-placeholder {
      padding: 2rem;
      color: var(--text-secondary);
    }
    h2 {
      font-size: var(--text-2xl);
      font-weight: 600;
      color: var(--text-primary);
      margin-bottom: 0.5rem;
    }
  `],
})
export class SettingsComponent {}
