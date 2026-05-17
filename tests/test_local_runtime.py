from __future__ import annotations

from pathlib import Path

import urllib.error

from backet.local_runtime import _post_json, local_runtime_doctor, run_local_runtime_benchmark


def test_local_runtime_doctor_reports_windows_amd_missing_ollama(monkeypatch) -> None:
    monkeypatch.setattr("backet.local_runtime.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        "backet.local_runtime._hardware_inventory",
        lambda: {
            "cpu": {"Name": "AMD Ryzen 7 7800X3D"},
            "system": {"TotalPhysicalMemory": 32 * 1024**3},
            "gpus": [{"Name": "AMD Radeon RX 7800 XT", "AdapterRAM": 16 * 1024**3}],
            "amd_gpus": [{"Name": "AMD Radeon RX 7800 XT"}],
        },
    )
    monkeypatch.setattr("backet.local_runtime._find_ollama_executable", lambda: None)
    monkeypatch.setattr("backet.local_runtime._find_llama_cpp_executable", lambda: None)
    monkeypatch.setattr("backet.local_runtime._get_json", _raise_unavailable)

    result = local_runtime_doctor()

    assert result.data["ollama"]["installed"] is False
    assert "winget install --id Ollama.Ollama" in result.data["ollama"]["install_actions"][0]
    assert result.data["profile_compatibility"]["profiles"]["rag-standard"]["compatible"] is False
    assert "local_runtime_ollama_missing" in {issue.code for issue in result.issues}


def test_local_runtime_doctor_marks_standard_ready_and_quality_missing_reranker(monkeypatch) -> None:
    monkeypatch.setattr("backet.local_runtime._hardware_inventory", lambda: {})
    monkeypatch.setattr("backet.local_runtime._find_ollama_executable", lambda: "H:/Tools/Ollama/ollama.exe")
    monkeypatch.setattr("backet.local_runtime._find_llama_cpp_executable", lambda: None)
    monkeypatch.setattr("backet.local_runtime._ollama_version", lambda path: "ollama version is 0.24.0")
    monkeypatch.setattr(
        "backet.local_runtime._get_json",
        lambda url, timeout_seconds: {
            "models": [
                {"name": "nomic-embed-text:latest", "model": "nomic-embed-text:latest", "size": 274302450},
                {"name": "llama3.2:3b", "model": "llama3.2:3b", "size": 2019393189},
            ]
        },
    )

    result = local_runtime_doctor()
    profiles = result.data["profile_compatibility"]["profiles"]

    assert result.data["ollama"]["api_available"] is True
    assert profiles["rag-standard"]["compatible"] is True
    assert profiles["rag-quality"]["compatible"] is False
    assert profiles["rag-quality"]["missing_roles"] == ["reranker"]


def test_local_runtime_benchmark_records_metrics_without_qa(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "backet.local_runtime.local_runtime_doctor",
        lambda **kwargs: _fake_doctor_result(),
    )
    monkeypatch.setattr(
        "backet.local_runtime._benchmark_embedding",
        lambda **kwargs: {"ok": True, "model": kwargs["model"], "latency_seconds": 0.1, "dimensions": 768},
    )
    monkeypatch.setattr(
        "backet.local_runtime._benchmark_generation",
        lambda **kwargs: {
            "ok": True,
            "model": kwargs["model"],
            "latency_seconds": 1.2,
            "tokens_per_second": 42.0,
            "response_preview": "A blood bond is a source-supported tie.",
        },
    )
    monkeypatch.setattr("backet.local_runtime._ollama_process_memory", lambda: {"available": True, "working_set_bytes": 123})

    result = run_local_runtime_benchmark(report_output=tmp_path)

    assert result.data["ok"] is True
    assert result.data["benchmarks"]["embedding"]["dimensions"] == 768
    assert result.data["hardware_recommendation"]["status"] == "standard_profile_ready"
    assert (tmp_path / "local-runtime-benchmark.json").exists()


def test_post_json_retries_transient_ollama_connection_close(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=_FakeErrorBody(
                    b'{"error":"read tcp 127.0.0.1:1->127.0.0.1:2: wsarecv: An existing connection was forcibly closed by the remote host."}'
                ),
            )
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.setattr("backet.local_runtime.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("backet.local_runtime.LOCAL_RUNTIME_RETRY_DELAYS", (0,))

    assert _post_json("http://127.0.0.1:11434/api/embed", {"model": "nomic"}, timeout_seconds=1) == {"ok": True}
    assert calls["count"] == 2


def _raise_unavailable(url: str, *, timeout_seconds: float):
    from backet.errors import AppError

    raise AppError(code="local_runtime_http_unavailable", message="unavailable")


def _fake_doctor_result():
    from backet.models import CommandResult

    return CommandResult(
        message="fake",
        data={
            "profile_compatibility": {
                "profiles": {
                    "rag-standard": {"compatible": True},
                    "rag-quality": {"compatible": False, "missing_roles": ["reranker"]},
                }
            }
        },
    )


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.body


class _FakeErrorBody:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        pass
