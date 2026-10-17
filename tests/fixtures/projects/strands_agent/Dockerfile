FROM --platform=linux/arm64 python:3.12-slim
RUN useradd --create-home --uid 10001 agent
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY agent.py ./
USER agent
EXPOSE 8080
CMD ["opentelemetry-instrument", "python", "agent.py"]
