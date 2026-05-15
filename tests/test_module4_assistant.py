"""
Tests for Module 4 — Ops Assistant
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "modules/module4"))
import ops_assistant as oa

def test_empty_key_is_rejected():
    with patch("sys.exit") as mock_exit, patch("builtins.print"):
        oa._validate_api_key("")
        mock_exit.assert_called_with(1)

def test_valid_key_passes():
    with patch("sys.exit") as mock_exit:
        oa._validate_api_key("gsk_" + "a" * 40)
        mock_exit.assert_not_called()

def test_error_never_exposes_api_key():
    import urllib.error
    fake_key = "gsk_" + "x" * 40
    oa.GROQ_API_KEY = fake_key
    mock_fp = MagicMock()
    mock_fp.read.return_value = b'{"error": {"message": "invalid"}}'
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
        url="", code=401, msg="Unauthorized", hdrs={}, fp=mock_fp
    )):
        result = oa.ask_llm({"services": []}, "test")
    assert fake_key not in result
    oa.GROQ_API_KEY = ""
