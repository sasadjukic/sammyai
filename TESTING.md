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
