# Installing from Source

Installing SammyAI from source is the best way to ensure you have the latest features and can contribute to the development of the tool.

## Prerequisites

Before you begin, ensure you have the following installed on your system:

*   **Python 3.10+**: SammyAI requires a modern Python environment.
*   **Git**: To clone the repository and manage updates.
*   **Ollama**: Required for running local LLMs like Gemma. Download it from [ollama.com](https://ollama.com).

## Step-by-Step Installation

### 1. Clone the Repository

Open your terminal or command prompt and run the following command to download the source code:

```bash
git clone https://github.com/sasadjukic/sammyai.git
cd sammyai
```

### 2. Create a Virtual Environment (Recommended)

It is highly recommended to use a virtual environment to keep SammyAI's dependencies separate from your system Python.

**On Linux/macOS:**
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

Install the required Python packages using `pip`:

```bash
pip install -r requirements.txt
```

### 4. Running SammyAI

Once the dependencies are installed, you can launch the application by running the main entry point:

```bash
python text_editor.py
```

> [!TIP]
> Make sure Ollama is running in the background if you plan to use local models during your session.

## Next Steps
Now that you have SammyAI running, head over to the [User Guide](file:///home/sasa/Desktop/Projects/sammyai_v1/documentation/3_USER_GUIDE/1_Getting_Started.md) to explore its features.
