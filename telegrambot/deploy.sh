#!/bin/bash

# Deploy script for Redex Game Bot with update capability

echo "Starting deployment of Redex Game Bot..."

# 1. Check and manage lock file
LOCK_FILE="/tmp/deploy.lock"
if [ -f "$LOCK_FILE" ]; then
    echo "Another deployment process is running. Stopping it..."
    kill -9 $(cat "$LOCK_FILE") 2>/dev/null
    rm -f "$LOCK_FILE"
    # Kill any running bot or web processes
    pkill -f "python3.*(bot.py|web.py)" 2>/dev/null
    sleep 2
fi
echo $$ > "$LOCK_FILE"

# 2. Update system and install prerequisites
echo "Updating system and installing prerequisites..."
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv mysql-server docker.io git

# 3. Start Docker service
echo "Starting Docker service..."
systemctl start docker
systemctl enable docker

# 4. Install Docker Compose
echo "Installing Docker Compose..."
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
curl -L "https://github.com/docker/compose/releases/download/v2.29.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# 5. Install Python modules with no cache and force reinstall
echo "Installing Python modules with no cache and force reinstall..."
pip3 install --no-cache-dir --force-reinstall "python-telegram-bot[job-queue]==22.3" mysql-connector-python==9.4.0 python-dotenv==1.1.1 requests==2.32.5 flask==3.1.1

# 6. Create project directory
echo "Creating project directory..."
mkdir -p /root/RedexGame/telegrambot
cd /root/RedexGame/telegrambot

# 7. Clone or update repository from GitHub
echo "Cloning or updating repository from GitHub..."
if [ -d ".git" ]; then
    git pull origin main
else
    git clone https://github.com/NoTredeX/RedexGame.git temp_repo
    cp -r temp_repo/telegrambot/* .
    rm -rf temp_repo
fi

# 8. Prompt for user input
echo "Please enter the required information:"
read -p "Enter BOT_TOKEN: " bot_token
read -p "Enter ADMIN_ID (numeric ID, e.g., 1631919159): " admin_id
read -p "Enter IPDNS1: " ipdns1
read -p "Enter IPDNS2: " ipdns2
echo "Enter MYSQL_PASSWORD (press Enter to generate a random password):"
read -s mysql_password
if [ -z "$mysql_password" ]; then
    mysql_password=$(openssl rand -base64 12)
    echo "Generated MYSQL_PASSWORD: $mysql_password"
fi

# 9. Create .env file with UTF-8 encoding and database host
echo "Creating .env file..."
cat > .env << EOL
BOT_TOKEN=$bot_token
ADMIN_ID=$admin_id
MYSQL_USER=root
MYSQL_PASSWORD=$mysql_password
IPDNS1=$ipdns1
IPDNS2=$ipdns2
MYSQL_HOST=db
EOL

# 10. Set up MySQL database
echo "Setting up MySQL database..."
mysql -u root << EOL
CREATE DATABASE IF NOT EXISTS dnsbot;
ALTER USER 'root'@'localhost' IDENTIFIED BY '$mysql_password';
GRANT ALL PRIVILEGES ON dnsbot.* TO 'root'@'localhost';
FLUSH PRIVILEGES;
EOL

# 11. Apply database schema directly with index check
echo "Applying database schema..."
mysql -u root -p"$mysql_password" dnsbot << 'EOL'
DROP INDEX IF EXISTS idx_services_telegram_id ON services;
DROP INDEX IF EXISTS idx_pending_payments_telegram_id ON pending_payments;
DROP INDEX IF EXISTS idx_pending_payments_service_id ON pending_payments;

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

# 12. Create docker-compose.yml
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
      MYSQL_USER: root
      MYSQL_PASSWORD: $mysql_password
    ports:
      - "3307:3306"
    volumes:
      - db_data:/var/lib/mysql
volumes:
  db_data:
EOL

# 13. Start Docker containers with delay
echo "Starting Docker containers with delay..."
docker compose up -d
sleep 10  # Wait for MySQL to start

# 14. Free port 5000 and set up Python virtual environment
echo "Freeing port 5000 and setting up Python virtual environment..."
fuser -k 5000/tcp 2>/dev/null
python3 -m venv venv
source venv/bin/activate
pip install --no-cache-dir -r requirements.txt
python3 bot.py &
FLASK_APP=web.py FLASK_RUN_PORT=5001 python3 -m flask run --no-debugger &
deactivate

# 15. Clean up lock file
rm -f "$LOCK_FILE"

echo "Deployment completed successfully!"
