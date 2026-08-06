# v1.4.9 France operational coverage

- Adds metropolitan France and Corsica as an enabled operational region.
- Adds French QRA and support base networking from the supplied reference.
- No broader EU or NATO regions are enabled.

# VNG Air Defense Operations Center v1.4.9

## v1.4.8 reliability and pre-scramble review

- Live WebSocket broadcasts are serialized and revision-safe.
- New consoles receive a full compact baseline before deltas.
- Collection ordering is preserved across keyed updates.
- During the final 30 seconds before an automatic communications-mismatch escalation, a compact shared review strip appears with **DENY AUTO ALERT**.
- Denial is limited to the current communications case; monitoring continues, while emergency and manual NORDO alerts remain immediate.

## v1.4.7 USCG BLACKJACK and DCA helicopter route reference

- Recognizes likely DCA-area BLACKJACK helicopters conservatively from callsign/remarks, helicopter type, and proximity.
- Adds a click-controlled **DCA HELI ROUTES** reference overlay for Washington Routes 1 and 5, the Broad Creek Transition, and the closed Route 4 segment.
- Links the FAA Baltimore–Washington Helicopter Route Chart effective July 9, 2026.
- Route geometry is situational reference only; the current FAA chart and live ATC instructions control.

## v1.4.7 permanent overlay removal, full aircraft details, and VSOA dispatch

- Permanently removed the legacy Selected Track / NORDO Workflow overlay and all hover-card reopen paths.
- Aircraft details are now click-only and appear in a compact structured popup beside the selected map track.
- Restored reported radio, expected controller/frequency, current squawk, assigned squawk, squawk comparison, route, and detector diagnostics in ATC Coordination.
- Replaced the cramped ATC aircraft text fields with styled native selectors for **My Live VSOA Aircraft** and **Target / Case Aircraft**.
- Live airborne VSOA-tagged aircraft can be selected as the operator aircraft and assigned directly to a selected target.
- The selection remains a shared VATSIM workflow label only and does not command aircraft or verify authorization.

## v1.4.3 alert evidence, timelines, stability, exemptions, and ATC layout

- ATC Coordination now includes a rule-by-rule alert evidence panel and chronological case timeline.
- Added frequency-change grace, configurable clear confirmation, and post-handoff cooldown logic to reduce alert flicker.
- Added shared, expiring temporary communications exemptions with operator, reason, and audit events.
- Added current/downstream ARTCC handoff details, boundary distance, estimated crossing, and projected handoff point on the ATC map.
- Rebuilt ATC panel grids and controls to wrap safely without overlapping or clipping at desktop, tablet, and phone widths.
- Preserves the v1.4.1 click-only map detail behavior and all v1.4.0 optimization features.

## v1.4.1 click-only map details and optimized architecture


- Aircraft detail cards are click-only by default, so moving across dense map traffic no longer opens a large menu.
- The `HOVER DETAILS` control can restore delayed hover cards; enabled cards wait 650 ms before opening.
- Hidden Situation Map, Intercepts, and ATC workspaces are marked dirty instead of being redrawn on every VATSIM feed cycle.
- ARTCC membership checks are cached per feed/boundary revision, with exact polygon checks still authoritative.
- ATC coverage candidates use a conservative spatial grid before exact geometry and radio-range validation.
- Automatic and manual intercept solutions reuse unchanged track signatures; **Recalculate Now** still forces a fresh solution.
- WebSocket clients receive keyed deltas after their initial snapshot, with periodic full snapshots for recovery.
- Frequent WebSocket pilot records omit selection-only diagnostic fields; selecting a track—or enabling optional hover details—retrieves the full record from `/api/tracks/{callsign}`.
- Shared operations, manual intercept assignments, intercept controls, manual NORDO designations, and incident state are stored in SQLite.
- Static assets use versioned URLs and immutable caching while `index.html` remains revalidated.
- Processing time now reports filter, ATC coverage, detection, and workflow stages.

### Railway persistence

Attach a Railway volume at `/app/data` and set `STATE_DB_PATH=/app/data/vng_adoc_state.sqlite3`. Without a volume, the SQLite feature still works during the running deployment but will not survive a replacement container.


## v1.3.37 online Center handoff suppression

- Suppresses false frequency-mismatch alerts when an aircraft is still inside the current ARTCC but has already been handed to an online neighboring Center.
- Requires the aircraft to be moving toward and projected to enter the neighboring ARTCC within 80 NM.
- Requires an exact match between a reported aircraft radio and the live downstream Center frequency.
- Does not whitelist random wrong frequencies, internal split-sector transitions, aircraft moving away from the boundary, or offline downstream Centers.


## Deployment verification

After Railway completes the deployment, verify these items before using the console:

1. The bottom status bar shows `BUILD v1.4.9`.
2. `/api/version` returns `france_operational_coverage: true`, `france_qra_bases: 6`, `live_deltas: true`, and `persistent_workflow: true`.
3. `/health` includes `processing_breakdown`.
4. The map toolbar displays `ARTCC FOCUS`, and the right rail has no Track / Intercept Data panel.

This ZIP is packaged with `Dockerfile`, `app/`, `tests/`, and the other project files at the archive root. Extract or copy those files directly into the GitHub repository root. Do not commit an outer version folder around them.

## v1.3.36 combined operator/ATC release with fixed map layout

- Merges the enhanced operator workflow, ATC Coordination Desk, live multi-interceptor tactical map, shared recalculation, and single-ARTCC focus mode into one build.
- Removes the legacy floating **Selected Track / NORDO Workflow** panel entirely so it cannot cover the situation map or operator queues.
- Keeps track review, NORDO controls, response state, coordination commands, notes, and intercept actions in the dedicated **ATC Coordination** and **Intercepts** workspaces.
- Fixes closed GeoJSON boundary handling so single-ARTCC focus correctly distinguishes inside, inbound, unrelated, and intercept-linked aircraft.
- Restores missing ATC tactical-map coordinate helpers and preserves both legacy and current recalculation callers.
- Uses a fixed, non-overlapping right rail containing only metrics and active alerts/watches.

## v1.3.34 single-ARTCC focus mode

- Select one ARTCC/FIR from the main map toolbar to filter the full operator dashboard.
- Retains tracks currently inside the selected boundary, inbound to an airport inside it, and aircraft linked by an active intercept mission.
- Filters alerts, NORDO watches, metrics, ATC cases, intercept assignments, controller counts, and map overlays to the focused center.
- Highlights only the selected ARTCC outline and provides a one-click clear action.


## v1.3.33 live multi-interceptor map and recalculation controls

- Added a dedicated tactical map inside the **Intercepts** workspace showing every active target, every assigned interceptor, each calculated route, and the latest anticipated intercept point.
- Multiple interceptors can be selected and assigned in one action; each remains visible with its own status, ETA, closure state, and recalculated solution.
- Added explicit **FIT ALL INTERCEPTS** and **RECALCULATE NOW** controls.
- Added visible live-link and last-recalculation indicators so operators can distinguish fresh solutions from stale display data.
- Force recalculation now rebuilds automatic and manual intercept geometry on the server, updates shared state, and broadcasts the revised solutions to all connected consoles.
- Hardened intercept action controls with busy states and success/error feedback to prevent duplicate requests and make button results visible.

## v1.3.31 intercept workspace, VSOA recommendations, and NORDO safeguards

- Added top-level **Situation Map**, **Active Intercept**, and **ATC Quick** workspaces so operators do not have to manage an active intercept through the narrow side rail.
- The Active Intercept workspace shows live target/interceptor heading, speed, altitude, separation, closure or opening rate, bearing, recommended course, turn required, altitude difference, and predictive intercept ETA.
- Target response can be shared across consoles as **Status Unknown**, **Responding**, **Not Responding**, or **Comms Restored**.
- Manual interceptor selection recommends airborne VSOA-tagged aircraft first, ranked by distance to the selected target, while still allowing any live VATSIM aircraft to be assigned.
- The ATC Quick workspace provides fast aircraft selection, radio review, manual NORDO confirmation, response-status controls, and intercept shortcuts.
- Automatic 122.800 monitoring now requires stable, high-confidence live ARTCC coverage. Any matching frequency from the valid active ARTCC coverage set whitelists the aircraft.
- A published CTAF/UNICOM/ATF match within 50 NM suppresses NORDO only for a plausible airport operating profile; high-altitude en-route traffic is not hidden merely because a nearby airport also uses 122.800.
- A projected early handoff to 122.800 is suppressed when the aircraft is leaving the current ARTCC within the configured 12-minute/90-NM lookahead and no downstream ARTCC is staffed.
- Floating ATC labels, popups, tooltips, and map controls are constrained to the visible map area to prevent edge clipping.
- Live online ATC sectors retain the solid high-contrast boundary, halo, interior tint, controller callsign, frequency, live dot, and `ONLINE` label introduced in v1.3.27.

Public VATSIM data cannot prove voice contact with 100% certainty. The system therefore labels automatic results as high-confidence possible NORDO and still requires human review.

## v1.3.26 manual intercept control

- Adds a shared **Intercept Control** console for manually pairing any two live VATSIM aircraft.
- Manual assignments override the selected interceptor's automatic target pairing while leaving other automatic intercepts intact.
- Live assignment cards show predictive intercept ETA, separation, signed closure/opening rate, recommended course, bearing, turn required, altitude delta, and both aircraft headings/speeds/altitudes.
- Assignments are shared across connected consoles, survive normal feed updates, and remain visible for five minutes when either track disconnects.
- Selected-track quick actions open the console with the target or interceptor prefilled.
- The shared response workflow now shows phase progress and one prominent **Next Action**, with the complete checklist available in an expandable section.

## v1.3.25 live viewer counter

A small footer indicator shows the number of unique browser consoles currently connected. The count is driven by active WebSocket presence, updates live, and deduplicates multiple tabs that share the same console identity.

Simulation-only VATSIM NORDO and intercept decision-support dashboard for the Virtual National Guard. Human review remains required before any virtual intercept action.


## v1.3.24 ATC activation alert-storm protection

- New communications-mismatch and 122.800 NORDO cases wait for 3 minutes of stable, high-confidence live ATC coverage before starting.
- Existing communications cases continue through normal Center handoffs and split-position changes.
- Newly active coverage is shown as an `ATC_ACTIVATION_GRACE` observation rather than filling the NORDO watch rail.
- Automatic scramble logic retains its separate 5-minute controller-stability and 8-minute eligible-mismatch safeguards.

## v1.3.23 VSOA remarks recognition release

This build expands flight-plan remarks recognition beyond the standalone `VSOA` token. Explicit organization markers such as `vUSCG`, `vRCAF`, `vUSAF`, `vUSN`, `vDHS`, `vNG`, `vNATO`, and other configured VSOA-style identifiers now receive the VSOA visual marker and navigation-detector mission exemption. The matched marker is shown in scope tags, tactical labels, popups, hover details, and the selected-aircraft panel.

Recognition is deliberately conservative. It requires a standalone configured marker or structured variant, rejects embedded lookalikes such as `NOTVUSCGTEST`, and remains a visual indication only; it does not verify VSOA membership or authorization.

## v1.3.22 radar-scope cleanup release

This build retains the v1.3.21 reliability audit changes and removes aircraft silhouettes from ATC Scope mode. Tactical mode continues to display aircraft-category shapes.

## v1.3.21 deep-audit changes

### NORDO case reliability

- `121.500` Guard never counts as ATC contact. `122.800` also does not count as ATC contact, but a verified nearby terminal CTAF/UNICOM match or a likely early handoff into an unstaffed ARTCC can suppress automatic escalation.
- A separate real ATC-frequency match still clears the case after the normal two-snapshot verification.
- Wrong-frequency timers advance only on fresh VATSIM snapshots. A network outage, Railway sleep, or stale feed cannot age a case toward a scramble flag.
- Communications history follows the aircraft session across Center sector changes and brief coverage gaps.
- A reused callsign cannot inherit another pilot's timer, manual NORDO designation, acknowledgment, or dismissal.
- Implausible position jumps reset the track session rather than joining unrelated movement histories.
- A valid frequency must appear in two consecutive snapshots before an active mismatch case clears.
- The selected-aircraft panel now includes an expandable **DETECTOR DIAGNOSTICS** section showing timer gates, last reset reason, suppressions, and all qualifying ATC coverage candidates.

### Stale-feed protection

- Warning state begins at 45 seconds by default.
- Critical stale state begins at 90 seconds by default.
- Critical stale state visibly marks all tracks as last-known positions and pauses new automatic alarm playback.
- `/health` distinguishes `initializing`, `ok`, `stale`, and `degraded` while remaining HTTP 200 for Railway health checks.

### Intercept workflow reliability

- Inbound-console records now use presence heartbeats.
- A console that closes without pressing Release automatically drops from the inbound count after the configured timeout.
- A heartbeat cannot rewind an operation from a later phase such as Fighters Airborne back to QRA Accepted.
- New occurrences of a reused alert ID receive a fresh responder list and checklist.

### QRA recommendations

- U.S. targets use U.S. QRA bases by default.
- Canadian targets use RCAF/NORAD bases by default.
- Every aircraft type assigned to a base is evaluated rather than assuming the first aircraft is always best.
- Cross-border recommendations remain disabled unless explicitly enabled.

### Browser and layout cleanup

- Fixed a startup JavaScript error that could stop the entire map before aircraft rendered.
- Added request timeouts and in-flight guards to prevent overlapping HTTP refreshes.
- Replaced multiple SUA retry loops with one controlled scheduler.
- Added a clear map-engine failure message if Leaflet cannot load.
- Mobile, tablet, and desktop layouts are width-contained with no horizontal page overflow.
- The main operations rail and panels remain resizable, with saved dimensions and a Reset Layout control.
- The map legend can be collapsed and its state is saved.
- Aircraft hover content remains lazy so large traffic loads do not rebuild hundreds of hidden cards each cycle.

### Security hardening before OAuth

- Cross-site shared-state mutation requests are blocked.
- Responses include `nosniff`, frame-denial, no-referrer, and restrictive browser-permission headers.
- This is not authentication. Until VATSIM OAuth and role checks are added, keep the dashboard URL limited to trusted operators.

## Current communications sequence

```text
Wrong frequency detected       → timer visible immediately
30 seconds                     → COMMS / NORDO WATCH
2 minutes on 122.800           → NORDO WATCH
3–5 minutes                    → POSSIBLE NORDO — INVESTIGATE
8 eligible minutes             → AUTO SCRAMBLE FLAG
```

The eight-minute timer is separate and only accumulates while the stricter IFR, altitude, speed, stable-ATC, reported-radio, and high-confidence coverage requirements are met.

## Center and terminal coverage

- All published parent U.S. and Canadian FIR/ARTCC outlines are shown as map references.
- Broad circular Center approximations are not drawn.
- Live radio-alert decisions still use live transceiver reach and facility hierarchy; a parent Center polygon alone does not prove exact sector ownership.
- Approach, Departure, Tower, Ground, and Delivery positions are supported.

## Mission-aware navigation detection

VSOA flights, recognized helicopters, and exact mission remarks such as SAR, Search and Rescue, Law Enforcement, Patrol, Orbit, Training, and Formation are exempt from orbit/loiter/route-deviation scoring. They are not exempt from emergency squawks, manual NORDO designation, or communications-mismatch monitoring.

## Deployment

Upload the complete folder to the GitHub branch connected to Railway. Do not merge only selected files from an older version. After deployment, perform a hard refresh with `Ctrl + Shift + R`.

See `DEPLOY_RAILWAY.md` and `.env.example` for recommended variables.

## v1.4.7 DCA / USCG additions

Use **DCA HELI ROUTES** on the Situation Map to show a public-landmark reference overlay and open the current FAA chart. The overlay is for VATSIM situational awareness only and is not a navigation or authorization source. Likely BLACKJACK tracks require a helicopter type, DCA-area proximity, and either the BLACKJACK/BJK callsign or explicit USCG + BLACKJACK flight-plan remarks.
