#!/bin/bash
#
# PiNode3 AWS-ver 用インストールスクリプト
#
# AWS IoT Core / S3 送信構成でのセットアップを行う。
# InfluxDBのインストール・rsync送信の設定は行わない。
#

### Pythonライブラリのインストール
sudo apt update
sudo apt install -y python3-opencv
sudo apt install -y swig liblgpio-dev build-essential
echo "=== pythonライブラリのインストール ==="
python -m venv venv
source venv/bin/activate
pip install -r "requirements.txt"

### USB判別ドライバのインストール
echo "=== USB判別ドライバのインストール ==="
model=$(grep -m1 -o -w 'Raspberry Pi [0-9]* Model [ABCD]\|Raspberry Pi 3 Model B Plus' /proc/cpuinfo)
echo "install $model USB driver"
if [[ "$model" == "Raspberry Pi 3 Model B" ]]; then
    sudo cp driver/usb/90-usb_3b.rules /etc/udev/rules.d/90-usb.rules
elif [[ "$model" == "Raspberry Pi 3 Model B Plus"* ]]; then
    sudo cp driver/usb/90-usb_3bp.rules /etc/udev/rules.d/90-usb.rules
elif [[ "$model" == "Raspberry Pi 4 Model B" ]]; then
    sudo cp driver/usb/90-usb_4b.rules /etc/udev/rules.d/90-usb.rules
else
    echo "This device is not a Raspberry Pi."
    exit 1
fi

### python・サービス・設定ファイル等を移行する
echo "=== Python/サービス/設定ファイルのコピー ==="
sudo cp service/* /etc/systemd/system/
mkdir -p /home/pinode3/data/sensor/lost
mkdir -p /home/pinode3/data/image/image1
mkdir -p /home/pinode3/data/image/image2
mkdir -p /home/pinode3/data/image/image3
mkdir -p /home/pinode3/data/image/image4
cp src/previous_sensor_data.json /home/pinode3/data
cp config.json /home/pinode3/

### コンフィグ設定
# device_id を pinodeXX (XX = 固定IPの第4オクテット) 形式で自動設定する
echo "=== コンフィグ設定 ==="
FOURTH_OCTET=$(hostname -I | awk '{print $1}' | awk -F. '{print $4}')
DEV_ID="pinode${FOURTH_OCTET}"
echo "DEVICE_ID = $DEV_ID"
sed -i "2s/\"00\"/\"$DEV_ID\"/" /home/pinode3/config.json

### サービスファイルの登録
echo "=== サービスファイルの登録 ==="
sudo systemctl daemon-reload
sudo systemctl enable data_collector.timer
sudo systemctl start data_collector.timer
sudo systemctl enable noon_monitor.timer
sudo systemctl start noon_monitor.timer

echo "=== インストール完了 ==="