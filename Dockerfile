#
FROM python:3.12-slim

#Creating a working directory inside the container 
WORKDIR /app

#Install uv inside the container environment
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

#Then copy the .toml file which contains the entire dependency as well as the sub dependency
COPY pyproject.toml ./
COPY README.md ./
COPY src/ ./src/

#To install the dependencies listed in the pyproject.toml
RUN uv pip install --system --no-cache-dir .


#Expose this port so that the application receices the network requests
EXPOSE 8000

# Render worker entrypoint: starts Celery and a minimal listener required by
# Render's Web Service port check. Compose service commands override this CMD.
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh
CMD ["/app/start.sh"]
