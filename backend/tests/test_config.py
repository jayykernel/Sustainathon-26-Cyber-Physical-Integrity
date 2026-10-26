"""Simple test for config loading to satisfy P0 requirements."""

from pathlib import Path

import pytest

from physiguard.config import Config, load_config

# Ensure we're loading from the project root, not the installed package
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "default.yaml"


def test_config_loads():
    """Test that config loads without error from default.yaml."""
    config = load_config(str(CONFIG_PATH))
    assert isinstance(config, Config)
    # Basic sanity check: plant capacity should be positive
    assert config.plant.Q > 0


def test_config_hash():
    """Test that config hash is computed."""
    config = load_config(str(CONFIG_PATH))
    hash_val = config.config_hash()
    assert isinstance(hash_val, str)
    assert len(hash_val) == 16  # truncated SHA256


def test_probe_key_environment_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The configured demo key is overridden when a process key is supplied."""
    monkeypatch.setenv("PHYSIGUARD_PROBE_KEY", "test-secret")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("probe:\n  key: yaml-secret\n", encoding="utf-8")

    assert load_config(config_path).probe.key == "test-secret"


def test_config_requires_yaml_mapping(tmp_path: Path) -> None:
    """Reject scalar YAML with a clear configuration error."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("- not-a-config-mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(config_path)
