import { Injectable, computed, signal } from '@angular/core';
import { ValidationDiscoveryData } from '../types/websocket';

@Injectable({ providedIn: 'root' })
export class ValidationStateApi {
  readonly activeContext = signal<ValidationDiscoveryData | null>(null);
  readonly cache = signal<Map<string, ValidationDiscoveryData>>(new Map());
  readonly activeCacheKey = signal<string | null>(null);
  readonly selectedOptions = signal<Map<string, Set<string>>>(new Map());

  // NEW: Validation history tracking
  readonly validationHistory = signal<ValidationDiscoveryData[]>([]);

  // NEW: Accordion management
  readonly expandedStepId = signal<number | null>(null);  // Currently expanded accordion (one at a time)
  readonly currentStepId = signal<number | null>(null);   // Currently highlighted/active validation

  readonly hasContext = computed(() => this.activeContext() !== null);

  upsertContext(context: ValidationDiscoveryData): string {
    const key = this._buildCacheKey(context);

    const cached = this.cache().get(key);
    const merged = cached ? this._mergeContext(cached, context) : context;
    const nextCache = new Map(this.cache());
    nextCache.set(key, merged);
    this.cache.set(nextCache);
    this.activeContext.set(merged);
    this.activeCacheKey.set(key);
    this._upsertHistory(key, merged);
    this.updateCurrentValidation(merged);  // NEW: Update accordion state
    this._logCache(cached ? 'cache-merge' : 'cache-upsert', key);
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
    this.clearHistory();
    this._logCache('cache-clear');
  }

  // NEW: Clear validation history
  clearHistory(): void {
    this.validationHistory.set([]);
    this._logCache('history-clear');
  }

  // Upsert context in history by cache key with cap at 100 items.
  private _upsertHistory(cacheKey: string, context: ValidationDiscoveryData): void {
    const history = [...this.validationHistory()];
    const existingIndex = history.findIndex((entry) => this._buildCacheKey(entry) === cacheKey);
    if (existingIndex >= 0) {
      history[existingIndex] = context;
    } else {
      history.push(context);
    }
    if (history.length > 100) {
      history.shift();
    }
    this.validationHistory.set(history);
  }

  private _mergeContext(previous: ValidationDiscoveryData, incoming: ValidationDiscoveryData): ValidationDiscoveryData {
    const prevOptions = previous.elementSnapshot.dropdownOptions ?? [];
    const incomingOptions = incoming.elementSnapshot.dropdownOptions ?? [];

    const shouldUseIncoming = incomingOptions.length >= prevOptions.length || !!incoming.isLateUpdate;
    if (!shouldUseIncoming) return previous;

    return {
      ...previous,
      ...incoming,
      elementSnapshot: {
        ...previous.elementSnapshot,
        ...incoming.elementSnapshot,
      },
      availableGroups: incoming.availableGroups?.length ? incoming.availableGroups : previous.availableGroups,
      matchedCatalogKeys: incoming.matchedCatalogKeys?.length ? incoming.matchedCatalogKeys : previous.matchedCatalogKeys,
    };
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

  // NEW: Get formatted step label (e.g., "1: CLICK")
  getStepLabel(stepId?: number, stepType?: string): string {
    if (stepId === undefined || !stepType) return '';
    return `${stepId}: ${stepType}`;
  }

  // Set expanded accordion directly to avoid UI toggle races.
  setExpandedStep(stepId: number | null): void {
    this.expandedStepId.set(stepId);
  }

  // NEW: Auto-expand and highlight when validation discovered
  updateCurrentValidation(context: ValidationDiscoveryData | null): void {
    if (context?.stepId !== undefined) {
      this.expandedStepId.set(context.stepId);  // Auto-expand accordion
      this.currentStepId.set(context.stepId);   // Highlight in blue
    }
  }

  private _buildCacheKey(context: ValidationDiscoveryData): string {
    if (context.validationId?.trim()) {
      return `validation:${context.validationId.trim()}`;
    }

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
      optionCount: value.availableGroups.reduce((count: number, group: { options: unknown[] }) => count + group.options.length, 0),
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