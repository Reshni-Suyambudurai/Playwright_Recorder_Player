import pytest

from app.utils.selector_builder import _GENERATED_ID_PATTERNS, _INSPECT_JS, is_stable_id


@pytest.mark.parametrize(
    "element_id",
    [
        "eefc5048-f311-4cc3-9a09-d52390761c04",
        "result-eefc5048-f311-4cc3-9a09-d52390761c04",
        "0123456789abcdef0123456789abcdef",
        "1727698045123",
    ],
)
def test_is_stable_id_rejects_generated_identifiers(element_id: str):
    assert is_stable_id(element_id) is False


@pytest.mark.parametrize(
    "element_id",
    [
        "checkout-button",
        "search-result-primary-link",
        "customer_email",
        "product-iphone-17-pro",
    ],
)
def test_is_stable_id_accepts_semantic_identifiers(element_id: str):
    assert is_stable_id(element_id) is True


def test_browser_inspector_uses_generated_id_rules():
    assert "__GENERATED_ID_CHECKS__" not in _INSPECT_JS
    for pattern in _GENERATED_ID_PATTERNS:
        assert f"/{pattern}/i.test(value)" in _INSPECT_JS