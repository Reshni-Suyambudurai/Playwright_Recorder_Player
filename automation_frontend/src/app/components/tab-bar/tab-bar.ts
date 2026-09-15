import { Component, OnInit, OnDestroy, inject, signal } from '@angular/core';
import { WebsocketApi } from '../../services/websocket.api';
import { TabInfo } from '../../types/websocket';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-tab-bar',
  standalone: true,
  templateUrl: './tab-bar.html',
  styleUrl: './tab-bar.css',
})
export class TabBar implements OnInit, OnDestroy {
  private wsApi = inject(WebsocketApi);
  private subs: Subscription[] = [];

  readonly tabs = signal<TabInfo[]>([]);
  readonly activeTabId = signal<string>('');

  ngOnInit(): void {
    this.subs.push(
      this.wsApi.tabOpened$.subscribe(data => {
        this.tabs.set(data.tabs ?? []);
        this.activeTabId.set(data.tab_id);
      }),
      this.wsApi.tabSwitched$.subscribe(data => {
        this.activeTabId.set(data.tab_id);
        // keep tabs list in sync
        const updated = this.tabs().map(t => ({ ...t, active: t.tab_id === data.tab_id }));
        this.tabs.set(updated);
      }),
      this.wsApi.recordingStarted$.subscribe(() => {
        this.tabs.set([{ tab_id: 'tab-1', title: 'Tab 1', url: '', active: true }]);
        this.activeTabId.set('tab-1');
      }),
      this.wsApi.recordingStopped$.subscribe(() => {
        this.tabs.set([]);
        this.activeTabId.set('');
      }),
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach(s => s.unsubscribe());
  }

  onTabClick(tabId: string): void {
    if (tabId !== this.activeTabId()) {
      this.wsApi.sendSwitchTab(tabId);
    }
  }

  tabLabel(tab: TabInfo, index: number): string {
    return tab.title?.trim() || `Tab ${index + 1}`;
  }
}
