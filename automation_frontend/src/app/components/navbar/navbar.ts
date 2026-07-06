import { Component, inject } from '@angular/core';
import { ThemeApi } from '../../services/theme.api';
import { SvgIcon } from '../svg-icon/svg-icon';
import { TooltipDirective } from '../../directives/tooltip/tooltip.directive';

@Component({
  selector: 'app-navbar',
  standalone: true,
  imports: [SvgIcon, TooltipDirective],
  templateUrl: './navbar.html',
  styleUrl: './navbar.css',
})
export class Navbar {
  private themeApi = inject(ThemeApi);

  readonly isDark = this.themeApi.isDark;
  readonly isSidebarOpen = this.themeApi.isSidebarOpen;

  toggleTheme(): void {
    this.themeApi.toggle();
  }

  toggleSidebar(): void {
    this.themeApi.toggleSidebar();
  }
}
