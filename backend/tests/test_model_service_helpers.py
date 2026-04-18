import base64

from model_service import _did_auth_headers, _model_uses_max_completion_tokens


def test_model_uses_max_completion_tokens_o_series():
    assert _model_uses_max_completion_tokens("o1-preview") is True
    assert _model_uses_max_completion_tokens("O3-mini") is True


def test_model_uses_max_completion_tokens_gpt4_mini():
    assert _model_uses_max_completion_tokens("gpt-4o-mini") is False


def test_did_auth_headers_basic_scheme():
    h = _did_auth_headers("my-api-key")
    assert h["Content-Type"] == "application/json"
    raw = base64.b64decode(h["Authorization"].replace("Basic ", "")).decode()
    assert raw == "my-api-key:"
