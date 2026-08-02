import { Injectable, computed, signal } from '@angular/core';
import { ValidationDiscoveryData } from '../types/websocket';

@Injectable({ providedIn: 'root' })
export class ValidationStateApi {
  readonly activeContext = signal<ValidationDiscoveryData | null>(null);
  readonly cache = signal<Map<string, ValidationDiscoveryData>>(new Map());
  readonly activeCacheKey = signal<string | null>(null);
  readonly selectedOptions = signal<Map<string, Set<string>>>(new Map());

  readonly hasContext = computed(() => this.activeContext() !== null);

  upsertContext(context: ValidationDiscoveryData): string {
    const key = this._buildCacheKey(context);

    const cached = this.cache().get(key);
    if (cached) {
      this.activeContext.set(cached);
      this.activeCacheKey.set(key);
      this._logCache('cache-hit', key);
      return key;
    }

    const nextCache = new Map(this.cache());
    nextCache.set(key, context);
    this.cache.set(nextCache);
    this.activeContext.set(context);
    this.activeCacheKey.set(key);
    this._logCache('cache-upsert', key);
    return key;
  }

  activateCacheKey(key: string): void {
    const cached = this.cache().get(key);
    if (!cached) return;
    this.activeContext.set(cached);
    this.activeCacheKey.set(key);
    this._logCache('cache-activate', key);
  }

  clear(): void {
    this.activeContext.set(null);
    this.activeCacheKey.set(null);
    this.cache.set(new Map());
    this.selectedOptions.set(new Map());
    this._logCache('cache-clear');
  }

  isSelected(groupKey: string, optionKey: string): boolean {
    const key = this.activeCacheKey();
    if (!key) return false;
    const groupSet = this.selectedOptions().get(key);
    return groupSet?.has(this._optionCompositeKey(groupKey, optionKey)) ?? false;
  }

  toggleOption(groupKey: string, optionKey: string): void {
    const cacheKey = this.activeCacheKey();
    if (!cacheKey) return;

    const nextSelected = new Map(this.selectedOptions());
    const nextGroupSet = new Set(nextSelected.get(cacheKey) ?? []);
    const compositeKey = this._optionCompositeKey(groupKey, optionKey);

    if (nextGroupSet.has(compositeKey)) {
      nextGroupSet.delete(compositeKey);
    } else {
      nextGroupSet.add(compositeKey);
    }

    nextSelected.set(cacheKey, nextGroupSet);
    this.selectedOptions.set(nextSelected);
    this._logCache('selection-toggle', cacheKey);
  }

  selectedLabels(): string[] {
    const cacheKey = this.activeCacheKey();
    const context = this.activeContext();
    if (!cacheKey || !context) return [];

    const selected = this.selectedOptions().get(cacheKey);
    if (!selected || selected.size === 0) return [];

    const labels: string[] = [];
    for (const group of context.availableGroups) {
      for (const option of group.options) {
        const compositeKey = this._optionCompositeKey(group.key, option.key);
        if (selected.has(compositeKey)) {
          labels.push(`${group.displayName}: ${option.displayName}`);
        }
      }
    }
    return labels;
  }

  private _buildCacheKey(context: ValidationDiscoveryData): string {
    const selector = context.elementSnapshot.selector;
    if (selector?.strategy && selector?.value) {
      return `selector:${selector.strategy}:${selector.value}:${selector.occurrence_index ?? 0}`;
    }

    const snapshot = context.elementSnapshot;
    const parts = [
      snapshot.tagName,
      snapshot.inputType ?? snapshot.type ?? '',
      snapshot.id ?? '',
      snapshot.name ?? '',
      snapshot.ariaLabel ?? snapshot.placeholder ?? snapshot.textContent ?? '',
    ];
    return `snapshot:${parts.join('|')}`;
  }

  private _optionCompositeKey(groupKey: string, optionKey: string): string {
    return `${groupKey}:${optionKey}`;
  }

  private _logCache(action: string, cacheKey: string | null = null): void {
    const cacheEntries = Array.from(this.cache().entries()).map(([key, value]) => ({
      key,
      elementCategory: value.elementCategory,
      isValidatable: value.isValidatable,
      matchedCatalogKeys: value.matchedCatalogKeys,
      groupCount: value.availableGroups.length,
      optionCount: value.availableGroups.reduce((count, group) => count + group.options.length, 0),
    }));

    const selectedEntries = Array.from(this.selectedOptions().entries()).map(([key, values]) => ({
      key,
      selected: Array.from(values),
    }));

    console.log('[ValidationCache]', {
      action,
      cacheKey,
      activeCacheKey: this.activeCacheKey(),
      activeContext: this.activeContext(),
      cacheEntries,
      selectedEntries,
    });
  }
}