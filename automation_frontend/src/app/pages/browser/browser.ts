import { Component, inject, signal } from '@angular/core';
import { Toolbar } from '../../components/toolbar/toolbar';
import { Status } from '../../components/status/status';
import { BrowserView } from '../../components/browser-view/browser-view';
import { RecordingModal } from '../../components/recording-modal/recording-modal';
import { ValidationPanel } from '../../components/validation-panel/validation-panel';
import { WebsocketApi } from '../../services/websocket.api';
import { StartRecordingData } from '../../types/websocket';

@Component({
  selector: 'app-browser',
  standalone: true,
  imports: [Toolbar, Status, BrowserView, RecordingModal, ValidationPanel],
  templateUrl: './browser.html',
  styleUrl: './browser.css',
})
export class BrowserComponent {
  private wsApi = inject(WebsocketApi);

  readonly showModal = signal(false);
  pendingUrl = '';

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
