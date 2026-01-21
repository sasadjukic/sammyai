# Running with Docker

Docker provides a seamless way to run SammyAI without worrying about installing Python, PySide6, or other dependencies on your local system.

> [!NOTE]
> **Status: Coming Soon!**
> We are currently putting the finishing touches on the official SammyAI Docker image. The instructions below will be fully functional as soon as the final release is pushed. Stay tuned!

## Prerequisites

*   [Docker](https://www.docker.com/products/docker-desktop/) installed and running on your system.

## How to Run

### 1. Pull the Image

Once released, you can download the latest SammyAI image using:

```bash
docker pull sasadjukic/sammyai:latest
```

### 2. Launch the Container

Since SammyAI is a GUI application, running it via Docker requires passing through your display settings:

**On Linux (X11):**
```bash
xhost +local:docker
docker run -it \
    --env DISPLAY=$DISPLAY \
    --volume /tmp/.X11-unix:/tmp/.X11-unix \
    sasadjukic/sammyai:latest
```

> [!IMPORTANT]
> If you are using local LLMs, ensure that your Docker container can communicate with the Ollama service running on your host machine (usually via `host.docker.internal`).

## Benefits of using Docker

*   **Isolated Environment**: No conflict with your existing Python projects.
*   **Easy Updates**: Simply pull the latest image to get new features.
*   **Portable**: Run the exact same environment on any OS that supports Docker.
