# Running with Docker

Docker can run SammyAI in an isolated environment. Because SammyAI is a desktop GUI application, Docker setup depends heavily on your operating system and display server.

## Prerequisites

* [Docker](https://www.docker.com/products/docker-desktop/) installed and running.
* A working display passthrough setup for GUI applications.
* Ollama reachable from the container if you plan to use local models.

## Pull the Image

```bash
docker pull sammycwa/sammyai:latest
```

## Launch on Linux with X11

```bash
xhost +local:docker
docker run -it \
    --env DISPLAY=$DISPLAY \
    --volume /tmp/.X11-unix:/tmp/.X11-unix \
    sammycwa/sammyai:latest
```

> [!IMPORTANT]
> If local models run on the host, configure the container so it can reach the host Ollama service. The correct hostname can vary by operating system and Docker setup.

## Benefits

* **Isolated environment:** Avoid conflicts with other Python projects.
* **Repeatable setup:** Use the same image across compatible machines.
* **Simple refresh:** Pull a newer image when one is published.
