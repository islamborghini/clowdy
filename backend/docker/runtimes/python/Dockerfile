# Base image for running user Python functions in Clowdy.
#
# This image is built once and reused for every function invocation.
# It contains Python 3.12 and the runner.py wrapper script.
#
# When a function is invoked, the backend:
#   1. Mounts the user's code at /app/function.py
#   2. Passes input via the INPUT_JSON environment variable
#   3. The container runs runner.py, which calls handler(input)
#   4. The result is printed to stdout as JSON
#
# Using python:3.12-slim keeps the image small (~50MB vs ~900MB for full).

FROM python:3.12-slim

WORKDIR /app

# Copy the runner script into the image
COPY runner.py /app/runner.py

# The container will execute runner.py when it starts
CMD ["python", "/app/runner.py"]
