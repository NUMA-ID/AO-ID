FROM python:3.11-slim

WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code de l'application
COPY . /app

ENV BASE_DOCX=/app/assets/TEMPLATE_BASE_ONEID.docx \
    DOC_BASE=/data/Documentation_Constructeur \
    OUT_DIR=/data/Documents_Generes \
    FICHES_DIR=/data/Fiches_Specs \
    ANTHROPIC_MODEL=claude-sonnet-4-6

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
