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

Writer-style regression tests cover migration/scope resolution, unchanged
no-profile prompts, all Writer stages and selection actions, provider delivery,
profile changes during a request, UI selection, review, and diagnostic privacy:

```powershell
.\Scripts\python.exe -B -u -m pytest -q tests/style_profiles tests/editor_workspace/test_writer_styles.py tests/llm_tests/test_system_prompt_delivery.py
```

The [profile acceptance record](documentation/7_NEXT_STEPS/15_Writer_Style_Profiles.md)
includes full-suite, installed-wheel, and isolated UI preview commands. The
preview uses temporary data and a fake provider. Writing quality and real-project
Windows acceptance are separate manual checks.

OpenAI adapter regressions use the installed OpenAI SDK with an offline HTTP
transport, so assertions inspect the serialized request body. They run in the
default suite and cover Luna's former `max_tokens: null` failure, reasoning-model
parameter policy, older/custom model behavior, error preservation, diagnostic
settings, Writer/Editor profile delivery, and every story-focused selection
action (including both custom result kinds). Ollama parameter regressions cover
local and cloud Gemma routing.

```powershell
.\Scripts\python.exe -B -u -m pytest -q tests/llm_tests/test_openai_adapter.py tests/llm_tests/test_system_prompt_delivery.py tests/diagnostics/test_provider_metadata.py
```

These tests do not call OpenAI or establish writing quality. Repeat the manual
profile comparison with `gpt-6-luna` after restarting SammyAI from this branch.
