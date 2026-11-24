FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 PORT=8000 OPEN_BROWSER=0 COOKIE_SECURE=1 DB_PATH=/data/siloti_stock.sqlite3
WORKDIR /app
COPY server.py ./server.py
COPY web ./web
COPY siloti_stock_data.json ./siloti_stock_data.json
COPY siloti_expense_data.json ./siloti_expense_data.json
EXPOSE 8000
CMD ["python", "server.py"]
