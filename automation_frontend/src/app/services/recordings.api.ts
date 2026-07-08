import { Injectable, inject } from '@angular/core';
import { TokenStore } from './token-store.api';
import { environment } from '../../environments/environment';
import { RecordingListItem, RecordingDetail } from '../types/websocket';

@Injectable({ providedIn: 'root' })
export class RecordingsApi {
  private tokenStore = inject(TokenStore);
  private base = environment.apiBaseUrl;

  async listRecordings(): Promise<RecordingListItem[]> {
    const clientId = this.tokenStore.getClientId();
    const res = await fetch(this.base + '/recording/list', {
      headers: clientId ? { 'x-client-id': clientId } : {},
    });
    if (!res.ok) throw new Error('List failed: ' + res.status);
    return res.json();
  }

  async getRecording(recordId: string): Promise<RecordingDetail> {
    const res = await fetch(this.base + '/recording/' + recordId);
    if (!res.ok) throw new Error('Load failed: ' + res.status);
    return res.json();
  }

  async deleteRecording(recordId: string): Promise<void> {
    const res = await fetch(this.base + '/recording/' + recordId, { method: 'DELETE' });
    if (!res.ok) throw new Error('Delete failed: ' + res.status);
  }

  async saveRecording(recordId: string, body: object): Promise<void> {
    const res = await fetch(this.base + '/recording/' + recordId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error('Save failed: ' + res.status);
  }
}
