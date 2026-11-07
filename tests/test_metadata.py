"""Marketplace release metadata and translation consistency checks."""

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "cay_gia_pha"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_keys(data, path=""):
    keys = set()
    if isinstance(data, dict):
        for name, value in data.items():
            child = f"{path}.{name}" if path else name
            keys.add(child)
            keys.update(_flatten_keys(value, child))
    return keys


def test_marketplace_release_structure_and_metadata():
    manifest = _read(INTEGRATION / "manifest.json")
    hacs = _read(ROOT / "hacs.json")
    assert manifest["domain"] == INTEGRATION.name
    assert manifest["config_flow"] is True
    assert manifest["single_config_entry"] is True
    assert manifest["integration_type"] == "service"
    assert hacs["homeassistant"] == "2026.11.0"
    assert manifest["version"] == "2026.11.0"
    assert (INTEGRATION / "frontend" / "cay-gia-pha-card.js").is_file()
    assert (INTEGRATION / "sensor.py").is_file()


def test_translations_have_matching_key_trees():
    base = _flatten_keys(_read(INTEGRATION / "strings.json"))
    for name in ("vi", "en"):
        translated = _flatten_keys(_read(INTEGRATION / "translations" / f"{name}.json"))
        assert translated == base, f"Translation keys differ in {name}"
