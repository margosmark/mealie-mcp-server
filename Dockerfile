FROM python:3.12-slim

WORKDIR /app

# Install the package itself so dependencies and the console script both come
# from pyproject.toml rather than a parallel requirements file.
COPY pyproject.toml README.md LICENSE ./
COPY mealie_mcp_server ./mealie_mcp_server
RUN pip install --no-cache-dir .

ENTRYPOINT ["mealie-mcp-server"]
