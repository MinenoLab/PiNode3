#!/bin/bash

### InfluxDBのインストール ###

# 上手く動作しない場合は以下のURLを参照
# https://docs.influxdata.com/influxdb/v2/install/?t=%3Cfont+style%3D%22vertical-align%3A+inherit%3B%22%3E%3Cfont+style%3D%22vertical-align%3A+inherit%3B%22%3ELinux%3C%2Ffont%3E%3C%2Ffont%3E
# https://www.influxdata.com/downloads/?_gl=1*tp92hm*_ga*OTYxNDc3OTA3LjE3MTA1NjEwMjY.*_ga_CNWQ54SDD8*MTcxNDYyNDU3Ny4yLjEuMTcxNDYyNTYxMi42MC4wLjUyNDc4MDY1Mg..

# すでにインストールされている場合はスキップ
if ! command -v influxd &> /dev/null; then
    echo "InfluxDB をインストールします..."
    
    wget -q https://repos.influxdata.com/influxdata-archive_compat.key
    echo '393e8779c89ac8d958f81f942f9ad7fb82a25e133faddaf92e15b16e6ac9ce4c influxdata-archive_compat.key' | sha256sum -c && \
    cat influxdata-archive_compat.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg > /dev/null
    echo 'deb [signed-by=/etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg] https://repos.influxdata.com/debian stable main' | sudo tee /etc/apt/sources.list.d/influxdata.list

    sudo apt-get -y update && sudo apt-get install -y influxdb2
    sudo systemctl start influxdb

    rm influxdata-archive_compat.key
else
    echo "InfluxDB はすでにインストールされています。"
fi

# InfluxDBのセットアップが完了しているかチェック
if ! influx bucket list --org pinode &> /dev/null; then
    echo "InfluxDB の初期セットアップを実行します..."
    
    influx setup \
        --username pinode \
        --password pinode-pass \
        --org pinode \
        --bucket pinode \
        --force
else
    echo "InfluxDB のセットアップはすでに完了しています。"
fi

# 認証トークンが存在しない場合のみ作成
TOKEN_FILE="src/token.txt"
if [ ! -f "$TOKEN_FILE" ]; then
    echo "新しい認証トークンを作成します..."
    influx auth create -o pinode --all-access | sed -n '2p' | awk '{print $2}' > "$TOKEN_FILE"
else
    echo "認証トークンはすでに存在しています。"
fi

echo "InfluxDBのインストールとセットアップが完了しました。"

### pythonライブラリのインストール
echo "=== pythonライブラリのインストール ==="
python -m venv pinode3 --system-site-packages
source pinode3/bin/activate
pip install -r "requirements.txt"

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
sudo cp service/* /etc/systemd/system/
mkdir -p /home/pinode3/data/sensor/lost
mkdir -p /home/pinode3/data/image/image1
mkdir -p /home/pinode3/data/image/image2
mkdir -p /home/pinode3/data/image/image3
mkdir -p /home/pinode3/data/image/image4
cp src/previous_sensor_data.json /home/pinode3/data
cp config.json /home/pinode3/

### サービスファイルの登録
echo === サービスファイルの登録 ===
sudo systemctl daemon-reload
sudo systemctl enable data_collector.timer
sudo systemctl start data_collector.timer
