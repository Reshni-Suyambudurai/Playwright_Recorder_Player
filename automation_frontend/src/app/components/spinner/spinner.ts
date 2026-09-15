import { Component, input } from '@angular/core';
import { NgClass } from '@angular/common';

@Component({
  selector: 'app-spinner',
  standalone: true,
  imports: [NgClass],
  templateUrl: './spinner.html',
  styleUrl: './spinner.css',
})
export class Spinner {
  /** Visual size: 'sm' = 20px, 'md' = 32px, 'lg' = 44px */
  size = input<'sm' | 'md' | 'lg'>('md');

  /**
   * When true, wraps the spinner in a full dark semi-transparent overlay
   * (used over the live browser screenshot). When false, renders inline.
   */
  overlay = input<boolean>(false);

  /** Ring colour — 'white' for dark overlays, 'primary' for light surfaces */
  color = input<'white' | 'primary'>('primary');
}
