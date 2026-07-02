import { Component, inject } from '@angular/core';
import { ThemeApi } from '../../services/theme.api';

@Component({
  selector: 'app-navbar',
  standalone: true,
  templateUrl: './navbar.html',
  styleUrl: './navbar.css',
})
export class Navbar {
  private themeApi = inject(ThemeApi);
  readonly isDark = this.themeApi.isDark;

  toggleTheme(): void {
    this.themeApi.toggle();
  }
}
