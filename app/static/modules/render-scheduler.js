(() => {
  const dirty = new Set(['map', 'intercept', 'atc']);
  function mark(...workspaces) { workspaces.forEach(name => dirty.add(name)); }
  function consume(name) { const result = dirty.has(name); dirty.delete(name); return result; }
  function isDirty(name) { return dirty.has(name); }
  globalThis.VngRenderScheduler = { mark, consume, isDirty };
})();
