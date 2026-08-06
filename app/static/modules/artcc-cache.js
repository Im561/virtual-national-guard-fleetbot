(() => {
  const values = new Map();
  let namespace = '';

  function reset(nextNamespace = '') {
    if (nextNamespace === namespace) return;
    namespace = nextNamespace;
    values.clear();
  }

  function membership(pilot, boundary, revision, contains) {
    const boundaryId = String(boundary?.id || 'NONE').toUpperCase();
    reset(`${boundaryId}|${revision ?? 'NA'}`);
    const key = [
      pilot?.callsign || '', Number(pilot?.lat).toFixed(5), Number(pilot?.lon).toFixed(5),
      Number(pilot?.arrival_lat).toFixed(5), Number(pilot?.arrival_lon).toFixed(5),
    ].join('|');
    if (values.has(key)) return values.get(key);
    const inside = Boolean(boundary?.geometry && contains(pilot?.lat, pilot?.lon, boundary.geometry));
    const inbound = Boolean(!inside && !pilot?.on_ground && boundary?.geometry && contains(pilot?.arrival_lat, pilot?.arrival_lon, boundary.geometry));
    const result = { inside, inbound, relevant: inside || inbound };
    values.set(key, result);
    return result;
  }

  globalThis.VngArtccCache = { membership, reset };
})();
