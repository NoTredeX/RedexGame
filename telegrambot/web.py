from flask import Flask, render_template, request, jsonify
import mysql.connector
import requests
import os
import time
import logging
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

logging.basicConfig(
    filename='web.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="127.0.0.1",
            port=3307,
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database="dnsbot"
        )
        logger.info("Database connection established")
        return conn
    except mysql.connector.Error as err:
        logger.error(f"Database connection error: {err}")
        return None

def is_iranian_ip(ip):
    try:
        api_key = os.getenv("IPGEOLOCATION_API_KEY")
        if not api_key:
            logger.error("IPGEOLOCATION_API_KEY not set in .env")
            return False
        url = f"https://api.ipgeolocation.io/ipgeo?apiKey={api_key}&ip={ip}&fields=country_code2"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        logger.info(f"IP check for {ip}: {data}")
        country_code = data.get("country_code2")
        if not country_code:
            logger.warning(f"No country_code2 for IP {ip}")
            return False
        return country_code.upper() == "IR"
    except requests.RequestException as e:
        logger.error(f"Request error for IP {ip}: {e}")
        return False
    except ValueError as e:
        logger.error(f"JSON decode error for IP {ip}: {e}")
        return False

@app.route("/register/<service_id>/<telegram_id>")
def register(service_id, telegram_id):
    logger.info(f"Register route called with service_id: {service_id}, telegram_id: {telegram_id}")
    return render_template("register.html", service_id=service_id, telegram_id=telegram_id)

@app.route("/api/get_client_ip")
def get_client_ip():
    ip = request.remote_addr
    logger.info(f"Client IP requested: {ip}")
    return jsonify({"ip": ip})

@app.route("/api/register_ip", methods=["POST"])
def register_ip():
    data = request.get_json()
    ip = data.get("ip")
    service_id = data.get("service_id")
    telegram_id = data.get("telegram_id")
    logger.info(f"Register IP called with ip: {ip}, service_id: {service_id}, telegram_id: {telegram_id}")

    time.sleep(1)
    if not is_iranian_ip(ip):
        logger.warning(f"IP {ip} is not Iranian")
        return jsonify({"success": False, "message": "اگر به فیلترشکن متصل هستید، آن را خاموش کنید"})

    time.sleep(1)
    conn = get_db_connection()
    if not conn:
        logger.error("Database connection failed")
        return jsonify({"success": False, "message": "!خطای سرور"})

    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE services SET ip_address = %s WHERE service_id = %s AND telegram_id = %s",
            (ip, service_id, telegram_id)
        )
        if cursor.rowcount == 0:
            logger.warning(f"No rows updated for service_id: {service_id}, telegram_id: {telegram_id}")
            return jsonify({"success": False, "message": "!سرویس یا کاربر پیدا نشد"})
        conn.commit()
        time.sleep(1)
        logger.info(f"IP {ip} registered successfully for service_id: {service_id}")
        return jsonify({"success": True, "message": "آی‌پی با موفقیت ثبت شد!"})
    except mysql.connector.Error as e:
        logger.error(f"Database error: {e}")
        return jsonify({"success": False, "message": "مشکلی پیش آمد، لطفاً دوباره امتحان کنید!..."})
    finally:
        if 'cursor' in locals():
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)