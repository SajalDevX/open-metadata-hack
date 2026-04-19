import importlib.util
from pathlib import Path


def _load_validator_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "validate_live_openmetadata.py"
    spec = importlib.util.spec_from_file_location("validate_live_openmetadata", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load validate_live_openmetadata.py module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_create_if_missing_default_is_true():
    module = _load_validator_module()
    parser = module._build_parser()
    args = parser.parse_args([])
    assert args.seed_create_if_missing is True


def test_seed_create_if_missing_can_be_disabled():
    module = _load_validator_module()
    parser = module._build_parser()
    args = parser.parse_args(["--no-seed-create-if-missing"])
    assert args.seed_create_if_missing is False


def test_seed_create_if_missing_can_be_enabled_explicitly():
    module = _load_validator_module()
    parser = module._build_parser()
    args = parser.parse_args(["--seed-create-if-missing"])
    assert args.seed_create_if_missing is True
