import { Component } from '@angular/core';
import { Toolbar } from '../../components/toolbar/toolbar';
import { Status } from '../../components/status/status';

@Component({
  selector: 'app-browser',
  standalone: true,
  imports: [Toolbar, Status],
  templateUrl: './browser.html',
  styleUrl: './browser.css',
})
export class BrowserComponent {}
