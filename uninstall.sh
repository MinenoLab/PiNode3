# USB判別ドライバの削除
sudo rm "/etc/udev/rules.d/90-usb.rules"

# サービスファイルの削除
sudo systemctl stop data_collector.timer
sudo systemctl disable data_collector.timer
sudo rm "/etc/systemd/system/data_collector.timer"
sudo rm "/etc/systemd/system/data_collector.service"
if [ -f "/etc/systemd/system/daily_rsync.timer" ]; then
    sudo systemctl stop daily_rsync.timer
    sudo systemctl disable daily_rsync.timer
    sudo rm "/etc/systemd/system/daily_rsync.timer"
    sudo rm "/etc/systemd/system/daily_rsync.service"
fi

# systemd のデーモンをリロード
sudo systemctl daemon-reload

echo "uninstall success"
