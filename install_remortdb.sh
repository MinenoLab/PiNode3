#!/bin/bash

### Pythonライブラリのインストール
sudo apt update
sudo apt install python3-opencv
echo "=== pythonライブラリのインストール ==="
python -m venv venv
source venv/bin/activate
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

# リモートInfluxDBの認証トークンの設定
TOKEN_FILE="src/token.txt"
echo "InfluxDBのトークンを入力してください。"
read -p "Token=" token
echo "$token" > "$TOKEN_FILE"

### rsyncによるデータのアップロード
echo === ssh公開鍵の登録 ===
ssh-keygen -t rsa -b 2048 -N "" -f ~/.ssh/pinode_key -q
echo "-> 接続先ホストのIPアドレスを入力してください。"
read -p "HOST :" HOST
echo "-> 接続先ユーザ名を入力してください。"
read -p "NAME :" NAME
ssh-copy-id -i ~/.ssh/pinode_key.pub "$NAME"@"$HOST"
ip_hyphen=$(hostname -I | awk '{gsub(/\./, "-");print $1}')
cat << EOF > "/home/pinode3/upload_files.sh"
#!/bin/bash
rsync -az -e "ssh -i /home/pinode3/.ssh/pinode_key" --rsync-path="mkdir -p /home/$NAME/$ip_hyphen/data && rsync" /home/pinode3/data/ $NAME@$HOST:/home/$NAME/$ip_hyphen/data/

EOF
chmod +x "/home/pinode3/upload_files.sh"

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

### コンフィグ設定
echo === コンフィグ設定 ===
DEV_ID=$(echo "$ip_hyphen" | cut -d'-' -f3-)
echo DEVICE_ID = "$DEV_ID"
echo HOST      = "$HOST"
sed -i "2s/00/$DEV_ID/" /home/pinode3/config.json
sed -i "4s/localhost/$HOST/" /home/pinode3/config.json

### サービスファイルの登録
echo === サービスファイルの登録 ===
sudo systemctl daemon-reload
sudo systemctl enable data_collector.timer
sudo systemctl start data_collector.timer
sudo systemctl enable daily_rsync.timer
sudo systemctl start daily_rsync.timer

