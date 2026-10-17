FROM python:3.12-slim
WORKDIR /app
COPY .env ./
COPY server.py ./
RUN pip install mcp
EXPOSE 5000
CMD ["python", "server.py"]
