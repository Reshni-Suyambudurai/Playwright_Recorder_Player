import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { ThemeApi } from '../../services/theme.api';
import { SvgIcon } from '../svg-icon/svg-icon';
import type { IconName } from '../svg-icon/svg-icon';
import { TooltipDirective } from '../../directives/tooltip/tooltip.directive';

interface SidebarItem {
  label: string;
  route: string;
  icon: IconName;
}

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, SvgIcon, TooltipDirective],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css',
})
export class Sidebar {
  private themeApi = inject(ThemeApi);
  readonly isOpen = this.themeApi.isSidebarOpen;

  readonly navItems: SidebarItem[] = [
    { label: 'Browser', route: '/', icon: 'browser' },
    { label: 'Flows', route: '/flows', icon: 'flows' },
    { label: 'Runs', route: '/runs', icon: 'runs' },
    { label: 'Settings', route: '/settings', icon: 'settings' },
  ];
}

