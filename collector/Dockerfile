FROM mcr.microsoft.com/playwright/python:v1.64.1-noble
RUN pip install --no-cache-dir playwright==1.64.1 gspread==6.2.1
WORKDIR /app
COPY . .
CMD ["python", "-u", "app.py"]
