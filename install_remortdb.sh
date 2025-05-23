#!/bin/bash

# リモートInfluxDBの認証トークンの設定
TOKEN_FILE="src/token.txt"
echo "InfluxDBのトークンを入力してください。"
read -p "Token=" token
echo "$token" > "$TOKEN_FILE"

### Pythonライブラリのインストール
# [仮想環境有効化]
# $ source /usr/local/bin/pinod3/python/pinode3/bin/activate
# [仮想環境無効化]
# $ deactivate
# [仮想環境削除]
# $ rm -rf /usr/local/bin/python/pinode3
echo "=== pythonライブラリのインストール ==="
python -m venv pinode3 --system-site-packages
source pinode3/bin/activate
pip install -r "requirements.txt"

mkdir -p /usr/local/bin/pinode3/python/
mv pinode3/ /usr/local/bin/pinode3/python/
deactivate

echo === USB判別ドライバのインストール ===
model=$(grep -m1 -o -w 'Raspberry Pi [0-9]* Model [ABCD]\|Raspberry Pi 3 Model B Plus' /proc/cpuinfo)
echo install $model USB driver
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
echo === Python/サービス/設定ファイルのコピー ===
sudo chmod 755 -R src/*
sudo cp src/* /usr/local/bin/pinode3
sudo chmod 777 service/*
sudo cp service/* /etc/systemd/system/
sudo mkdir -p /home/pinode3/data/sensor/lost
sudo mkdir -p /home/pinode3/data/image/image1
sudo mkdir -p /home/pinode3/data/image/image2
sudo mkdir -p /home/pinode3/data/image/image3
sudo mkdir -p /home/pinode3/data/image/image4
sudo cp src/previous_sensor_data.json /home/pinode3/data
sudo cp config.json /home/pinode3/
sudo chmod 666 /home/pinode3/config.json
sudo chmod -R 777 /home/pinode3/data

### サービスファイルの登録
echo === サービスファイルの登録 ===
sudo systemctl daemon-reload
sudo systemctl start data_collector.timer
sudo systemctl start data_collector.service

