FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY extractor ./extractor
COPY samples ./samples
ENTRYPOINT ["python", "-m", "extractor"]
CMD ["samples/", "--out", "output/", "--format", "csv", "json", "sqlite"]
