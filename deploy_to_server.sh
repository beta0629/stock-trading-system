#!/bin/bash

# 실제 서버 배포 스크립트
# 사용법: ./deploy_to_server.sh [username]

# 설정
SERVER_IP="45.76.16.239"
USERNAME=${1:-"linuxuser"}  # 기본값: linuxuser
REMOTE_DIR="/home/linuxuser/stock_trading"
LOCAL_DIR="/Users/mind/stock_sale"

echo "===== 주식 거래 시스템 배포 시작 ====="
echo "서버 IP: $SERVER_IP"
echo "사용자: $USERNAME"
echo "원격 디렉토리: $REMOTE_DIR"

# 배포 준비: 필요한 파일 압축
echo "필요한 파일 압축 중..."
cd "$LOCAL_DIR" || exit 1
rm -f stock_sale_deploy.zip
zip -r stock_sale_deploy.zip . -x "*.git*" "*.DS_Store" "node_modules/*" "*/node_modules/*" "venv/*" "*/__pycache__/*" "*.pyc" "*.log" "logs/*" "cache/*" "data/backup/*"

# 서버에 원격 디렉토리 생성 확인
echo "서버에 디렉토리 생성 중..."
ssh "$USERNAME@$SERVER_IP" "mkdir -p $REMOTE_DIR"

# 압축 파일 전송
echo "파일 전송 중..."
scp stock_sale_deploy.zip "$USERNAME@$SERVER_IP:$REMOTE_DIR/"

# 서버에서 압축 해제 및 설정
echo "서버에서 파일 설치 중..."
ssh "$USERNAME@$SERVER_IP" "cd $REMOTE_DIR && \
    unzip -o stock_sale_deploy.zip && \
    rm stock_sale_deploy.zip && \
    chmod +x run_stock_trader.sh && \
    pip3 install -r requirements.txt"

# 서버에서 서비스 설정
echo "서비스 설정 중..."
ssh "$USERNAME@$SERVER_IP" "cd $REMOTE_DIR && \
    if [ ! -f /etc/systemd/system/stock-api.service ]; then
        cat > /tmp/stock-api.service << 'EOL'
[Unit]
Description=Stock Trading API Server
After=network.target

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$REMOTE_DIR
ExecStart=/usr/bin/python3 $REMOTE_DIR/api_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL
        sudo mv /tmp/stock-api.service /etc/systemd/system/
        sudo systemctl daemon-reload
    fi && \
    if [ ! -f /etc/systemd/system/stock-trader.service ]; then
        cat > /tmp/stock-trader.service << 'EOL'
[Unit]
Description=Stock Trading System
After=network.target stock-api.service
Requires=stock-api.service

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$REMOTE_DIR
ExecStart=/usr/bin/python3 $REMOTE_DIR/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL
        sudo mv /tmp/stock-trader.service /etc/systemd/system/
        sudo systemctl daemon-reload
    fi"

# 서비스 재시작
echo "서비스 재시작 중..."
ssh "$USERNAME@$SERVER_IP" "sudo systemctl enable stock-api.service && \
    sudo systemctl enable stock-trader.service && \
    sudo systemctl restart stock-api.service && \
    sudo systemctl restart stock-trader.service"

# 상태 확인
echo "서비스 상태 확인 중..."
ssh "$USERNAME@$SERVER_IP" "sudo systemctl status stock-api.service --no-pager && \
    sudo systemctl status stock-trader.service --no-pager"

echo "===== 배포 완료 ====="
echo "서버에서 다음 명령어로 로그 확인 가능:"
echo "  API 서버 로그: sudo journalctl -u stock-api.service -f"
echo "  거래 시스템 로그: sudo journalctl -u stock-trader.service -f"