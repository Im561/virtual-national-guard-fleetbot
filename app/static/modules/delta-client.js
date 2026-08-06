(() => {
  const collectionKeys = {
    pilots: item => String(item?.callsign || '').toUpperCase(),
    alerts: item => String(item?.id || item?.callsign || '').toUpperCase(),
    operations: item => String(item?.id || item?.callsign || ''),
    manual_intercepts: item => String(item?.assignment_id || item?.interceptor_callsign || '').toUpperCase(),
    intercept_controls: item => String(item?.target_callsign || '').toUpperCase(),
    temporary_exemptions: item => String(item?.id || ''),
    controllers: item => String(item?.callsign || '').toUpperCase(),
  };

  function applyCollection(previous, patch, keyFn) {
    const values = new Map((previous || []).map(item => [keyFn(item), item]).filter(([key]) => key));
    for (const key of patch?.remove || []) values.delete(String(key));
    for (const item of patch?.upsert || []) {
      const key = keyFn(item);
      if (key) values.set(key, item);
    }
    if (!Array.isArray(patch?.order)) return [...values.values()];
    const ordered = [];
    const seen = new Set();
    for (const rawKey of patch.order) {
      const key = String(rawKey);
      if (!values.has(key) || seen.has(key)) continue;
      ordered.push(values.get(key));
      seen.add(key);
    }
    for (const [key, item] of values) {
      if (!seen.has(key)) ordered.push(item);
    }
    return ordered;
  }

  function applyDelta(previous, delta) {
    if (!previous || delta?.type !== 'delta') return null;
    if (Number(previous.revision) !== Number(delta.base_revision)) return null;
    const next = { ...previous, ...(delta.changes || {}), type: 'live', revision: delta.revision };
    for (const [name, patch] of Object.entries(delta.collections || {})) {
      const keyFn = collectionKeys[name];
      if (keyFn) next[name] = applyCollection(previous[name], patch, keyFn);
    }
    return next;
  }

  globalThis.VngDeltaClient = { applyDelta };
})();
