import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-rectangle-drawer',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './rectangle-drawer.html',
  styleUrls: ['./rectangle-drawer.css'],
})
export class RectangleDrawerComponent implements OnInit {
  @Input() isActive: boolean = false;
  @Input() rect: { x: number; y: number; width: number; height: number } = {
    x: 0,
    y: 0,
    width: 0,
    height: 0,
  };

  ngOnInit(): void {
    // Component initialization if needed
  }
}
