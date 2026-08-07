from backend.config import _is_loopback_url


def test_loopback_ollama_endpoint_detection_is_strict() -> None:
    assert _is_loopback_url("http://127.0.0.1:11434/v1/") is True
    assert _is_loopback_url("http://localhost:11434/v1/") is True
    assert _is_loopback_url("http://[::1]:11434/v1/") is True
    assert _is_loopback_url("http://192.168.1.20:11434/v1/") is False
    assert _is_loopback_url("https://ollama.example.com/v1/") is False
    assert _is_loopback_url("https://localhost.example.com/v1/") is False
