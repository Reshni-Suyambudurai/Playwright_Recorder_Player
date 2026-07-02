import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

interface SidebarItem {
  label: string;
  route: string;
  icon: string;
}

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css',
})
export class Sidebar {
  readonly navItems: SidebarItem[] = [
    { label: 'Browser', route: '/', icon: 'browser' },
    { label: 'Flows', route: '/flows', icon: 'flows' },
    { label: 'Runs', route: '/runs', icon: 'runs' },
    { label: 'Settings', route: '/settings', icon: 'settings' },
  ];
}
