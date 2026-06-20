import pytest

from trading.kis_auth import validate_credentials


@pytest.mark.parametrize("mode", ["prod", "vps"])
def test_validate_credentials_treats_app_key_prefix_as_opaque(mode):
    valid, message = validate_credentials("PSN_SAMPLE_KEY_12345", mode)

    assert valid is True
    assert message == ""


@pytest.mark.parametrize("app_key", ["", "short"])
def test_validate_credentials_rejects_missing_or_short_key(app_key):
    valid, message = validate_credentials(app_key, "vps")

    assert valid is False
    assert "empty or too short" in message
