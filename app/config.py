from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "VNG Air Defense Operations Center"
    # VATSIM's public feed normally advances in short snapshots. Ten-second
    # polling catches a new snapshot quickly without making the browser redraw
    # when the feed timestamp has not changed.
    poll_seconds: int = 10
    http_fallback_seconds: int = 15
    monitor_canada: bool = True
    monitor_france: bool = True
    enable_live_deltas: bool = True
    delta_full_snapshot_interval: int = 30
    spatial_grid_degrees: float = 5.0
    state_db_path: str = "data/vng_adoc_state.sqlite3"
    state_persist_debounce_seconds: float = 0.35

    vatsim_data_url: str = "https://data.vatsim.net/v3/vatsim-data.json"
    vatsim_transceiver_url: str = "https://data.vatsim.net/v3/transceivers-data.json"
    aviation_weather_airport_url: str = "https://aviationweather.gov/api/data/airport"
    vatspy_boundaries_url: str = "https://raw.githubusercontent.com/vatsimnetwork/vatspy-data-project/master/Boundaries.geojson"
    tracon_boundaries_url: str = "https://github.com/vatsimnetwork/simaware-tracon-project/releases/latest/download/TRACONBoundaries.geojson"
    atc_boundary_refresh_seconds: int = 21600
    sua_feature_url: str = "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/ArcGIS/rest/services/Special_Use_Airspace/FeatureServer/0"
    sua_refresh_seconds: int = 21600
    canada_airspace_index_url: str = "https://soaringweb.org/Airspace/NA/HomePage.html"
    user_agent: str = "VNG-ADOC/1.4.9 contact=operator@example.invalid"

    center_coverage_radius_nm: float = 350.0
    approach_coverage_radius_nm: float = 100.0
    # Alert coverage is derived from live AFV transceiver reach. Facility
    # polygons remain a display/geographic guard only.
    center_alert_max_range_nm: float = 230.0
    approach_alert_max_range_nm: float = 110.0
    tower_alert_max_range_nm: float = 18.0
    ground_alert_max_range_nm: float = 6.0
    tower_max_agl_ft: int = 5000
    ground_track_max_speed_kt: int = 45
    ground_airport_radius_nm: float = 8.0
    ground_track_max_msl_ft: int = 12000
    atc_overlap_margin: float = 0.18
    # AFV publishes frequencies as integer Hz. Keep the match tolerance narrow
    # enough that adjacent 8.33/25 kHz channels cannot be mistaken as equal.
    frequency_match_tolerance_hz: int = 1500
    # A reported CTAF/UNICOM/ATF frequency is a valid advisory assignment when
    # the aircraft is within this radius of the matching airport. It does not
    # count as ATC contact, but it suppresses automatic NORDO escalation.
    advisory_frequency_whitelist_radius_nm: float = 50.0
    advisory_frequency_whitelist_max_altitude_ft: int = 12000
    advisory_frequency_whitelist_max_groundspeed_kt: int = 250
    # Centers may release an aircraft to 122.800 before the exact FIR boundary
    # when no downstream Center is staffed. Project the current track this far
    # ahead and suppress automatic NORDO if it exits the active ARTCC into an
    # unstaffed or unsupported downstream boundary.
    early_unicom_handoff_lookahead_minutes: int = 12
    early_unicom_handoff_max_lookahead_nm: float = 90.0
    # Normal Center-to-Center handoffs may occur before the exact ARTCC line.
    # Suppress a mismatch only when the aircraft is projected to cross the
    # current ARTCC boundary within this distance and a reported radio exactly
    # matches the online downstream Center it is entering.
    online_center_handoff_max_distance_nm: float = 80.0
    online_center_handoff_probe_step_nm: float = 2.0
    atc_require_unambiguous_controller: bool = True
    atc_polygon_only_alerts: bool = False
    atc_split_fallback_alerts: bool = False
    min_airborne_altitude_ft: int = 3000
    # Aggressive-but-staged communications monitoring. A verified wrong-
    # frequency condition is visible immediately, enters the watch rail after
    # two stable feed snapshots, and escalates well before the eight-minute
    # automatic scramble flag.
    frequency_mismatch_observe_seconds: int = 30
    frequency_mismatch_observe_min_altitude_ft: int = 5000
    frequency_mismatch_observe_min_groundspeed_kt: int = 80
    frequency_mismatch_observe_require_ifr: bool = True
    # Newly staffed ATC coverage receives a short settling window before it can
    # create a new communications-mismatch case. This prevents a Center login
    # from placing every pre-existing 122.800 track into the watch rail at once.
    # Existing cases continue through normal handoffs and split changes.
    communications_atc_min_online_seconds: int = 180
    # Stability controls prevent one transient AFV snapshot or a recently
    # completed Center handoff from immediately reopening a communications case.
    communications_clear_match_snapshots: int = 2
    communications_frequency_change_grace_seconds: int = 25
    communications_handoff_cooldown_seconds: int = 120
    temporary_exemption_default_minutes: int = 15
    temporary_exemption_max_minutes: int = 120
    nordo_advisory_seconds: int = 120
    nordo_warning_seconds: int = 300
    nordo_investigate_after_switch_seconds: int = 180
    nordo_investigate_seconds: int = 300
    nordo_previous_match_window_seconds: int = 1800
    nordo_min_altitude_ft: int = 5000
    nordo_min_groundspeed_kt: int = 80
    nordo_terminal_exclusion_nm: float = 55.0
    nordo_terminal_exclusion_max_altitude_ft: int = 12000
    nordo_terminal_exclusion_max_groundspeed_kt: int = 250
    nordo_require_ifr: bool = True
    nordo_require_high_confidence_coverage: bool = True
    # Automatic scramble flag: a high-priority operator alert only. It does
    # not launch or connect an interceptor. Its separate eligible timer starts
    # only after the controlling position has been continuously online long
    # enough to avoid false flags when ATC has just logged on.
    auto_scramble_frequency_mismatch_seconds: int = 480
    auto_scramble_atc_min_online_seconds: int = 300
    auto_scramble_min_altitude_ft: int = 10000
    auto_scramble_min_groundspeed_kt: int = 150
    auto_scramble_require_ifr: bool = True
    auto_scramble_require_reported_radio: bool = True
    auto_scramble_require_high_confidence_coverage: bool = True
    # Give operators one final shared review window before a communications-
    # only automatic scramble alert enters the alert queue. A denial is scoped
    # to the current aircraft/session communications case and cannot suppress
    # manual NORDO designations or emergency squawks.
    pre_scramble_warning_seconds: int = 30
    pre_scramble_denial_record_ttl_seconds: int = 1800
    # Timers advance only on fresh observed snapshots. This prevents a Railway
    # sleep, network outage, or stale VATSIM response from aging a case forward.
    max_observed_feed_tick_seconds: int = 30
    communications_case_gap_seconds: int = 60
    manual_nordo_stale_seconds: int = 180
    feed_stale_warning_seconds: int = 45
    feed_stale_critical_seconds: int = 90
    # Keep QRA recommendations inside the target country unless an operator
    # explicitly enables cross-border NORAD recommendations.
    allow_cross_border_qra_recommendations: bool = False
    console_presence_heartbeat_seconds: int = 30
    console_presence_timeout_seconds: int = 105
    route_deviation_nm: float = 180.0
    route_deviation_seconds: int = 600
    enable_route_deviation_alerts: bool = False
    navigation_anomalies_observation_only: bool = True
    destination_arm_distance_nm: float = 60.0
    destination_overshoot_nm: float = 25.0
    orbit_detection_window_seconds: int = 900
    orbit_detection_min_duration_seconds: int = 600
    orbit_detection_turn_degrees: float = 600.0
    orbit_detection_max_displacement_nm: float = 18.0
    orbit_detection_max_radius_nm: float = 22.0
    orbit_detection_min_points: int = 20
    orbit_detection_min_altitude_ft: int = 3000
    orbit_detection_min_groundspeed_kt: int = 60
    # Prevent normal SID turns, vectors, procedure turns, and initial-climb
    # reversals from contributing to an orbit/intercept indication.
    orbit_departure_suppression_nm: float = 80.0
    orbit_departure_suppression_seconds: int = 1500
    orbit_departure_suppression_max_altitude_ft: int = 24000
    orbit_turn_direction_consistency: float = 0.72
    orbit_detection_min_net_turn_degrees: float = 500.0
    orbit_nordo_corroboration_seconds: int = 300
    assigned_squawk_mismatch_seconds: int = 120
    monitored_zone_lookahead_minutes: int = 10
    whitelisted_squawks: str = "1200,2000"
    enable_missing_radio_alert: bool = False
    missing_radio_seconds: int = 300
    scramble_alarm_confidence: int = 90
    # Multiple automatic frequency-mismatch tracks under the same ARTCC are
    # one communications incident. Only the first track sounds; the incident
    # resets after the ARTCC has no qualifying tracks for this many seconds.
    scramble_incident_reset_seconds: int = 300
    # When multiple new automatic communications flags appear together, keep
    # every aircraft visible in the NORDO watch rail but require additional
    # fresh, stable feed observations before any automatic scramble escalation.
    mass_alert_guard_threshold: int = 2
    mass_alert_guard_window_seconds: int = 60
    mass_alert_guard_verify_seconds: int = 45
    mass_alert_guard_min_snapshots: int = 3
    mass_alert_guard_record_ttl_seconds: int = 300
    alert_queue_min_confidence: int = 60
    alert_min_independent_categories: int = 2

    @property
    def whitelisted_squawk_set(self) -> set[str]:
        return {
            item.strip().zfill(4)
            for item in self.whitelisted_squawks.split(",")
            if item.strip()
        }


settings = Settings()
