# Recording environment for the README demo: VHS plus excludarr from this checkout.
# Build and record from the repo root:
#   docker build -t excludarr-demo -f docs/demo/Dockerfile .
#   docker run --rm -v "$PWD/docs/demo:/vhs" excludarr-demo demo.tape
FROM ghcr.io/charmbracelet/vhs:v0.12.1
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
COPY pyproject.toml README.md /src/
COPY src /src/src
RUN uv venv -p 3.12 /opt/venv && uv pip install -p /opt/venv --no-cache /src
ENV PATH=/opt/venv/bin:$PATH
