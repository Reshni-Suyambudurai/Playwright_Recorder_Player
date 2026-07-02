import { Routes } from '@angular/router';
import { BrowserComponent } from './pages/browser/browser';
import { Flows } from './pages/flows/flows';
import { Runs } from './pages/runs/runs';
import { SettingsComponent } from './pages/settings/settings';

export const routes: Routes = [
  { path: '', component: BrowserComponent },
  { path: 'flows', component: Flows },
  { path: 'runs', component: Runs },
  { path: 'settings', component: SettingsComponent },
  { path: '**', redirectTo: '' },
];
