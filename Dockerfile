FROM python:3.12-slim

WORKDIR /app

# Abhaengigkeiten zuerst (Layer-Cache)
COPY app/requirements.txt /app/app/requirements.txt
RUN pip install --no-cache-dir -r /app/app/requirements.txt

# Restlicher Code (wird zur Laufzeit ohnehin per Volume gemountet)
COPY . /app

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
