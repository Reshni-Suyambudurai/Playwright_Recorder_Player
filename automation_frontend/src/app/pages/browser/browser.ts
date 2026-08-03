import { Component, inject, signal, OnInit, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
import { Toolbar } from '../../components/toolbar/toolbar';
import { Status } from '../../components/status/status';
import { BrowserView } from '../../components/browser-view/browser-view';
import { RecordingModal } from '../../components/recording-modal/recording-modal';
import { ValidationPanel } from '../../components/validation-panel/validation-panel';
import { WebsocketApi } from '../../services/websocket.api';
import { ValidationStateApi } from '../../services/validation-state.api';
import { StartRecordingData } from '../../types/websocket';

@Component({
  selector: 'app-browser',
  standalone: true,
  imports: [Toolbar, Status, BrowserView, RecordingModal, ValidationPanel],
  templateUrl: './browser.html',
  styleUrl: './browser.css',
})
export class BrowserComponent implements OnInit, OnDestroy {
  private wsApi = inject(WebsocketApi);
  private validationState = inject(ValidationStateApi);
  private subscription?: Subscription;

  readonly showModal = signal(false);
  pendingUrl = '';

  ngOnInit(): void {
    // NEW: Subscribe to recording stopped event and clear validation history
    this.subscription = this.wsApi.recordingStopped$.subscribe(() => {
      this.validationState.clearHistory();
    });
  }

  ngOnDestroy(): void {
    // NEW: Clean up subscription on destroy
    this.subscription?.unsubscribe();
  }

  onOpenModal(url: string): void {
    this.pendingUrl = url;
    this.showModal.set(true);
  }

  onModalConfirm(data: StartRecordingData): void {
    this.showModal.set(false);
    this.wsApi.sendStartRecording({ ...data, url: this.pendingUrl });
  }

  onModalCancel(): void {
    this.showModal.set(false);
  }
}
