#!/bin/bash

# Deploy script for Redex Game Bot

echo "Starting deployment of Redex Game Bot..."

# 1. Update system and install prerequisites
echo "Updating system and installing prerequisites..."
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv mysql-server docker.io docker-compose-plugin git

# 2. Install required Python modules with specific versions
echo "Installing Python modules..."
pip3 install python-telegram-bot==22.3 mysql-connector-python==9.4.0 python-dotenv==1.1.1 requests==2.32.5 flask==3.1.1

# 3. Create project directory
echo "Creating project directory..."
mkdir -p /root/RedexGame/telegrambot
cd /root/RedexGame/telegrambot

# 4. Clone repository from GitHub
echo "Cloning repository from GitHub..."
git clone https://github.com/NoTredeX/RedexGame.git temp_repo
cp -r temp_repo/telegrambot/* .
rm -rf temp_repo

# 5. Prompt for user input
echo "Please enter the required information:"
read -p "Enter BOT_TOKEN: " bot_token
read -p "Enter MYSQL_USER: " mysql_user
read -s -p "Enter MYSQL_PASSWORD: " mysql_password
echo
read -p "Enter IPDNS1: " ipdns1
read -p "Enter IPDNS2: " ipdns2

# 6. Create .env file with UTF-8 encoding
echo "Creating .env file..."
cat > .env << EOL
BOT_TOKEN=$bot_token
MYSQL_USER=$mysql_user
MYSQL_PASSWORD=$mysql_password
IPDNS1=$ipdns1
IPDNS2=$ipdns2
EOL

# 7. Set up MySQL database
echo "Setting up MySQL database..."
mysql -u root -p << EOL
CREATE DATABASE IF NOT EXISTS dnsbot;
GRANT ALL PRIVILEGES ON dnsbot.* TO '$mysql_user'@'localhost' IDENTIFIED BY '$mysql_password';
FLUSH PRIVILEGES;
EOL

# 8. Apply database schema directly
echo "Applying database schema..."
mysql -u "$mysql_user" -p"$mysql_password" dnsbot << 'EOL'
CREATE TABLE IF NOT EXISTS users (
    telegram_id VARCHAR(255) PRIMARY KEY,
    blocked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS services (
    service_id VARCHAR(36) PRIMARY KEY,
    telegram_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    purchase_date DATETIME NOT NULL,
    expiry_date DATETIME NOT NULL,
    duration INT NOT NULL,
    status ENUM('active', 'expired') NOT NULL,
    is_test BOOLEAN DEFAULT FALSE,
    deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS pending_payments (
    payment_id VARCHAR(36) PRIMARY KEY,
    telegram_id VARCHAR(255) NOT NULL,
    service_id VARCHAR(36) NOT NULL,
    service_name VARCHAR(255) NOT NULL,
    duration INT NOT NULL,
    price INT NOT NULL,
    caption TEXT,
    status ENUM('pending', 'approved', 'rejected') NOT NULL,
    reason TEXT,
    is_renewal BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id),
    FOREIGN KEY (service_id) REFERENCES services(service_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_services_telegram_id ON services(telegram_id);
CREATE INDEX idx_pending_payments_telegram_id ON pending_payments(telegram_id);
CREATE INDEX idx_pending_payments_service_id ON pending_payments(service_id);
EOL

# 9. Create docker-compose.yml
echo "Creating docker-compose.yml..."
cat > docker-compose.yml << EOL
version: '3'
services:
  db:
    image: mysql:5.7
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: $mysql_password
      MYSQL_DATABASE: dnsbot
      MYSQL_USER: $mysql_user
      MYSQL_PASSWORD: $mysql_password
    ports:
      - "3307:3306"
    volumes:
      - db_data:/var/lib/mysql
volumes:
  db_data:
EOL

# 10. Start Docker containers
echo "Starting Docker containers..."
docker-compose up -d

# 11. Set up Python virtual environment and run bot
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 bot.py &
python3 web.py &
deactivate

echo "Deployment completed successfully!"
