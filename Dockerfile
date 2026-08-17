FROM python:3.12-slim

# tesseract for the image-import OCR fallback
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 2000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "2000"]
