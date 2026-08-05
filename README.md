# PiNode3 (AWS版)
PiNode3は温室ハウス内で動作するデータ収集システムです．

# 実行環境

### OS要件
動作確認済みOSは以下です．
```
No LSB modules are available.
Distributor ID: Debian
Description:    Debian GNU/Linux 12 (bookworm)
Release:        12
Codename:       bookworm
```

確認方法
``` bash
$ sudo apt-get install lsb-release
$ lsb_release -a
```

# Raspberry Piの準備

Raspberry Pi本体側のOS書き込みと初期設定について記述します．
すでにセットアップ済みの場合は本章を飛ばして「インストール」に進んでください．

### Raspi OSのインストール
Raspberry Pi OSのインストーラは Raspberry Pi Imager を用いて作成します．
以下のリンクよりダウンロード＆インストールしてください．

[Raspberry Pi Imager](https://www.raspberrypi.com/software/)

インストール手順
1. 書き込み用MicroSDカードをPCに挿入する
2. Raspberry Pi Imagerを起動する
3. OSを選択する（**Raspberry Pi OS (64bit)**）
4. 書き込み用MicroSDカードを選択する
5. 指示に従ってOSイメージを書き込む

書き込み時設定
- OS : Raspberry Pi OS (64bit)
- ホスト名 : 固定IPアドレスの下2桁を付ける（例：`pinode50`）
- ユーザ名 : `pinode3`
- パスワード : 任意
- Wi-Fi設定（SSID / パスワード / 国：JP）
- ロケール設定（タイムゾーン：`Asia/Tokyo` / キーボード：`jp`）

### IPアドレスの固定
RaspiのIPアドレスを固定するため，`nmcli`で設定します．
まず，現在の接続名を確認します．
``` bash
$ nmcli con show
```
表示された接続名（例：`netplan-eth0`）に対して，以下を順に実行してIPアドレス・ゲートウェイ・DNSを設定し，
手動設定モードに切り替えたうえで自動接続を有効化します（値は環境に合わせて書き換えてください）．

<!-- 間違っているやつ
``` bash
$ sudo nmcli con mod "netplan-eth0" ipv4.addresses "192.168.XX.YY/24"
$ sudo nmcli con mod "netplan-eth0" ipv4.gateway   "192.168.XX.1"
$ sudo nmcli con mod "netplan-eth0" ipv4.dns       "192.168.XX.1 8.8.8.8"
$ sudo nmcli con mod "netplan-eth0" ipv4.method manual
$ sudo nmcli con mod "netplan-eth0" connection.autoconnect yes
$ sudo nmcli con up  "netplan-eth0"
``` -->

``` bash
$ sudo nmcli con mod "netplan-eth0" ipv4.addresses "192.168.XX.YY/24"
$ sudo nmcli con mod "netplan-eth0" ipv4.dns "8.8.8.8"
$ sudo nmcli con mod "netplan-eth0" ipv4.method manual
$ sudo nmcli con mod "netplan-eth0" connection.autoconnect yes
$ sudo nmcli con mod "netplan-eth0" ipv4.never-default yes
```

次に，VPNサブネット（例：192.168.200.0/24）宛のみeth0宛ゲートウェイに向けるようにします．

``` bash
$ sudo nmcli con mod "netplan-eth0" +ipv4.routes "192.168.200.0/24 192.168.XX.1"
```

最後に設定を反映します．

``` bash
$ sudo nmcli con up "netplan-eth0"
```

### IPアドレス割り当てルール
| 位置 | 例 | 割り当て |
| --- | --- | --- |
| 第1・第2オクテット | `192.168` | プライベートネットワーク（固定値） |
| 第3オクテット `XX` | `23` | ネットワークセグメントの識別番号 |
| 第4オクテット `YY` | `50` | PiNode個体番号 |

- ゲートウェイは同一セグメントのルータ（例：`192.168.XX.1`）を指定します．
- DNSは1つ目に同セグメントのルータ，2つ目に外部DNS（例：`8.8.8.8`）を指定します．

設定後，以下のコマンドでIPアドレスを確認してください．
``` bash
$ ip route
```

### SSH・I2C・SPI有効化
温度・湿度・照度データはI2C，果実径・茎径データはSPIを用いて取得しています．
Raspberry PiではデフォルトでI2C/SPIおよびSSHが無効化されているため，有効化する必要があります．
``` bash
$ sudo raspi-config
```
`Interfacing Options` から `SSH` / `I4 I2C` / `I3 SPI` をそれぞれ有効化し，リブートで反映されます．

``` bash
$ sudo reboot
```

### PCからのアクセス
Raspiに直接キーボード・モニタを繋がず，PCからSSHで操作する場合の手順です．

**PowerShellでSSH接続**
``` powershell
> ssh pinode3@192.168.*.*
```

同一のネットワーク環境下にある場合，ホスト名を指定しても接続可能です．
ただし，VPN経由で接続している場合，名前解決できない可能性があります．

**VSCode Remote-SSH で接続（複数回アクセスする場合）**
1. VSCode に Remote-SSH 拡張機能をインストールする
2. `~/.ssh/config` に以下を追加する
    ```text
    Host pinodeXX
        HostName 192.168.*.*
        User pinode3
    ```
3. VSCodeから「ホストに接続する」→ `pinodeXX` を選択

# インストール

以降の作業はSSH接続したRaspi上で行います．

### リポジトリのクローン
本リポジトリをクローンします．
> [!IMPORTANT]
> 現在の `main` ブランチはAWS IoT Core / S3への送信には対応していないため，`AWS-ver` ブランチを使用してください．

``` bash
$ git clone -b AWS-ver https://github.com/MinenoLab/PiNode3.git
$ cd PiNode3
```

### config.jsonの設定
`config.json`の `aws_iot` / `s3` セクションを利用環境に合わせて書き換えます．
``` json
"aws_iot": {
    "endpoint":             "xxxx.iot.ap-northeast-1.amazonaws.com",
    "credentials_endpoint": "xxxx.credentials.iot.ap-northeast-1.amazonaws.com",
    "cert_dir":             "/etc/iot",
    "field_id":             "daiwa-field-04",
    "project_id":           "daiwa",
    "device_type":          "PiNode",
    "wilt_device_id":       ""
},
"s3": {
    "bucket_name": "agri-data-bucket"
}
```

 `device_id` はインストールスクリプトで自動設定されるため，手動編集は不要です．


### ソフトウェアインストール
インストールスクリプトを実行して，必要なソフトウェアのインストールとサービス登録を行います．

#### a. AWS上へのデータ送信 + rsyncを用いて接続先ホスト（sakigake）に収集データの自動バックアップを行う場合
`install_with_rsync.sh` を実行します．
``` bash
$ cd PiNode3
$ bash install_with_rsync.sh
```
実行中に，rsync送信先ホストの情報を入力します．
- `HOST`：接続先ホストのIPアドレス（VPN経由アクセスのゲートウェイになるホスト 例：192.168.200.51）
- `NAME`：接続先ホストのユーザ名（例：sakigake）

<インストール時に以下のタイマの有効化・起動>
    - `data_collector.timer`（センサ値・画像の収集）
    - `daily_rsync.timer`（rsyncによる日次アップロード）
    - `noon_monitor.timer`（正午に画角調整を実行）

#### b. AWS上へのデータ送信のみの場合
rsync連携が不要な場合，`install.sh` を実行します．
``` bash
$ cd PiNode3
$ bash install.sh
```
<インストール時に以下のタイマの有効化・起動>
    - `data_collector.timer`（センサ値・画像の収集）
    - `noon_monitor.timer`（正午に画角調整を実行）


### （研究室向け）AWS IoT証明書の配置
AWS IoT CoreおよびS3への送信にはIoTデバイス証明書を使用します．
開発PC（例：dnn24）から証明書を`/etc/iot/`配下に転送してください．

```
/etc/iot/
├── cert.pem       # デバイス証明書
├── private.key    # 秘密鍵
└── root-CA.pem    # Amazon Root CA
```

# データ収集と確認

データ収集は`data_collector.timer`によりRaspiの起動と同時にスケジュール実行されます．
収集した値と画像は，`data_collector.py`から以下の2経路で送信されます．

- **S3**：センサJSON（`{projectID}/{fieldID}/{deviceID}/sensors/{timestamp}.json`）と画像
- **MQTT (AWS IoT Core)**：DynamoDBへのセンサ値送信

正常に動作しているかは以下のコマンドで確認できます．

収集データのローカル保存確認
``` bash
$ ls -l /home/pinode3/data/image/image*
$ ls -l /home/pinode3/data/sensor/
```

サービスの状態確認
``` bash
$ sudo systemctl status data_collector.service
$ journalctl -u data_collector.service -e
```

カメラが認識されていない場合は，以下でUSB接続を確認してください．
``` bash
$ ls /dev/ttyUSB*
```
カメラ名の割当ルールは`driver/usb/`以下のudevルールに記載されています．

# 送信間隔の変更

収集タイマは`/etc/systemd/system/data_collector.timer`で管理されています．
間隔を変更する場合は以下のようにファイルを編集してください．
``` bash
$ sudo nano /etc/systemd/system/data_collector.timer
```
``` ini
[Unit]
Description=Collect Image and Sensor
[Timer]
OnCalendar=*:0/5           # 5分ごとに実行
RandomizedDelaySec=180     # 他機器との送信混雑を避けるため0〜180秒ランダムに遅延
```

編集後はサービスを再起動してください．
``` bash
$ sudo systemctl daemon-reload
$ sudo systemctl restart data_collector.timer
```


以上でインストールは環境です．その他の設定等は[こちら](https://github.com/MinenoLab/PiNode3/blob/main/docs/source/get-started/index.rst)を参照してください．

# トラブルシューティング

### 時刻設定
時刻がずれていると，収集データのタイムスタンプがずれ，AWSで受信する際にエラーが発生します．
以下で確認し，必要に応じてタイムゾーンを設定してください．
``` bash
$ date
$ timedatectl
$ sudo timedatectl set-timezone Asia/Tokyo
```

### サービスファイルのハング対応
何らかの原因でエラーが発生した際に，サービスファイルがハングしてデータ収集・送信が止まることがあります．
以下の手順で確認してください．

サービスファイルのログの確認
``` bash
$ journalctl -u data_collector.service -f
```

サービスファイルの終了
``` bash
$ sudo systemctl stop data_collector.timer
$ sudo systemctl stop data_collector.service
```

`data_collector.service` に実行時間の上限を設定し，ハング時に自動で強制終了されるようにします．

```bash
$ sudo tee /etc/systemd/system/data_collector.service.d/override.conf > /dev/null <<'EOF'
[Service]
TimeoutStartSec=180
RuntimeMaxSec=180
TimeoutStopSec=30
KillMode=control-group
EOF
```

変更の反映

```bash
$ sudo systemctl daemon-reload
$ sudo systemctl reset-failed data_collector.service
```

override設定を反映後，手動実行して動作確認

```bash
$ sudo systemctl start data_collector.service
```

実行結果のログを出力し，`S3センサJSON送信完了` や `Deactivated successfully` が表示されているかを確認

```bash
$ journalctl -u data_collector.service -e --no-pager
```

問題なければタイマを再開して自動実行に戻す

```bash
$ sudo systemctl start data_collector.timer
```

### Spresenseが認識されない
デバイスマネージャの「ポート（COMとLPT）」に `Silicon Labs CP210x USB to UART Bridge` が表示されているかを確認してください．
表示されない場合はUSBドライバの再インストールを行います．

### COMポートの認識エラー
画像取得時にCOMポートエラーが出る場合は，Spresense以外のCP210xデバイスが接続されていないか確認してください．
必要に応じて`PiNode3-SPRESENSE/python/lib/SpresenseCameraChecker.py`の除外条件を編集します．
``` python
com_ports = [port for port in com_ports if "CP210" in port.description]
```

### ボード書き込みエラー（pgmspace.h が無い）
`pgmspace.h`が見つからずエラーになる場合は，以下からダウンロードして配置してください．
[pgmspace.h](https://github.com/Patapom/Arduino/blob/master/Libraries/AVR%20Libc/avr-libc-2.0.0/include/avr/pgmspace.h)

配置先：`Arduino/libraries/FastFRC/src/pgmspace.h`

# （参考）Spresenseカメラのセットアップ

USBカメラの代わりにSpresenseカメラを使用する場合は，以下の別リポジトリを開発PCにクローンし，
Arduino IDEでSpresenseに書き込む必要があります．

``` bash
$ git clone https://github.com/MinenoLab/PiNode3-SPRESENSE.git
```

参考：[Spresense開発者向けドキュメント](https://developer.spresense.sony-semicon.com/development-guides/?page=arduino_set_up&lang=ja)

### 1. Arduino IDEのインストール
[Arduino公式サイト](https://www.arduino.cc/en/software/) からArduino IDEをダウンロードしてインストールします．

### 2. USBドライバのインストール
[CP210x Universal Windows Driver](https://github.com/sonydevworld/spresense-hw-design-files/raw/master/misc/usb-to-uart-bridge-vcp-drivers/CP210x_Universal_Windows_Driver-v11.1.0.zip) をダウンロードしてインストールします．

### 3. SPRESENSE Arduino board packageのインストール
Arduino IDE起動後，以下の手順で追加します．
1. 「ファイル」→「基本設定」を選択
2. 「追加のボードマネージャのURL」に以下を追加してOK
    ```
    https://github.com/sonydevworld/spresense-arduino-compatible/releases/download/generic/package_spresense_index.json
    ```
3. 「ツール」→「ボード」→「ボードマネージャ」で `spresense` を検索し，`SPRESENSE Reference Board`をインストール（Packetizerはエラーが出た場合のみインストール）

### 4. Spresenseへの書き込み
1. SpresenseカメラをPCのUSBに接続
2. 「ツール」→「ボード」→「SPRESENSE Reference Board」→「Spresense」を選択
3. 「ツール」→「シリアルポート」でSpresenseのポートを選択
4. 「ツール」→「Memory」→「1536KB」を選択
5. 「ツール」→「UploadSpeed」→「115200」を選択
6. 「ツール」→「書き込み装置」→「Spresense Firmware Updater」を選択
7. 「ツール」→「ブートローダーを書き込む」を実行
8. 書き込み完了後，`PiNode3-SPRESENSE/Arduino.ino`を開き，「マイコンボードへ書き込む」を実行

### 5. PCからの動作確認
Spresense書き込み完了後，PCの仮想環境から動作を確認できます．
``` bash
$ cd PiNode3-SPRESENSE/python
$ pip install -r requirements.txt
$ python image_checker.py
```