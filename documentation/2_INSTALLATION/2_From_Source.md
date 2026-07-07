# Installing from Source

Installing SammyAI from source is the recommended alpha workflow.

## Prerequisites

Before you begin, install:

* **Python 3.11-3.14:** SammyAI requires Python `>=3.11,<3.15`.
* **Git:** Required to clone the repository and manage updates.
* **Ollama:** Required if you plan to run local models. Download it from [ollama.com](https://ollama.com).
* **PDF text extraction support:** PDF context features require the project dependencies and a working text extraction path.

## Step-by-Step Installation

### 1. Clone the Repository

```bash
git clone https://github.com/sasadjukic/sammyai.git
cd sammyai
```

### 2. Create a Virtual Environment

Using a virtual environment keeps SammyAI dependencies separate from your system Python.

**On Linux or macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**

```bash
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install Dependencies

Install SammyAI in editable mode:

```bash
python -m pip install -e .
```

For development and tests:

```bash
python -m pip install -e ".[test]"
```

### 4. Run SammyAI

Launch the application:

```bash
sammyai
```

You can also run directly from the source checkout:

```bash
python sammyai.py
```

The older `python text_editor.py` command remains as a compatibility launcher.

> [!TIP]
> Start Ollama before launching SammyAI if you plan to use local models.

## Next Steps

After SammyAI opens, create or open a project folder and continue with the User Guide in `documentation/3_USER_GUIDE/1_Layout.md`.
