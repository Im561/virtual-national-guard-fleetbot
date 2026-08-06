import re
from pathlib import Path


def test_v1333_operator_and_atc_workflows_are_present_and_wired():
    root = Path(__file__).parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    main = (root / "app" / "main.py").read_text(encoding="utf-8")

    for element_id in (
        "intercepts-select-nearest",
        "intercepts-assign-best-vsoa",
        "atc-quick-summary" if False else "atc-summary-cases",
        "atc-map",
        "atc-map-focus-selected",
        "atc-map-fit-related",
        "atc-load-first-case",
        "atc-open-intercepts",
    ):
        assert f'id="{element_id}"' in index

    for function_name in (
        "selectNearestInterceptors",
        "assignBestVsoaInterceptor",
        "atcRecommendedAction",
        "atcControllerRowsHtml",
        "ensureAtcOpsMap",
        "renderAtcOpsMap",
    ):
        assert f"function {function_name}" in js or f"async function {function_name}" in js

    assert "data-target-control" in js
    assert "data-save-intercept-note" in js
    assert "data-atc-open-intercept" in js
    assert ".atc-quick-summary" in css
    assert "#atc-map" in css
    assert 'APP_VERSION = "1.4.8"' in main
    assert '"version": APP_VERSION' in main


def test_all_direct_button_listeners_reference_existing_elements():
    root = Path(__file__).parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    html_ids = set(re.findall(r'id="([^"]+)"', index))
    listener_ids = set(re.findall(r"el\('([^']+)'\)\.addEventListener", js))
    assert listener_ids - html_ids == set()
