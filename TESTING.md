# Testing SammyAI

Install the development dependencies:

```bash
python -m pip install -e ".[test]"
```

The default suite is deterministic and does not require credentials, network
access, or an embedding-model download:

```bash
python -m pytest
```

Run model-backed RAG tests separately:

```bash
python -m pytest -m "model and not external"
```

Tests marked `external` require configured credentials or a running provider
such as Ollama and are never part of the default CI gate:

```bash
python -m pytest -m external
```

Diagnostics regression coverage is included in the default suite. Run its core,
context and Qt integration tests directly with:

```powershell
.\Scripts\python.exe -m pytest -q tests/diagnostics tests/context_engine/test_context_diagnostics.py tests/editor_workspace/test_diagnostics.py
```

The [diagnostics acceptance record](documentation/7_NEXT_STEPS/9_Chat_Agent_Diagnostics.md)
contains offline wheel checks and the synthetic screenshot command. These tests
use temporary databases/projects and mocked completions, never real providers or
the user's application data.
