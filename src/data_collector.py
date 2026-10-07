"""
データ収集のメインスクリプト

センサ値・収集状態・画像を取得し、以下の2経路に送信する（並行稼働）:
  - S3   : センサJSONを直接PUT（新・本命の経路）
  - MQTT : IoT Core経由でDynamoDBへ（既存・当面残す）

S3側が安定して動作することを確認できたら、MQTT送信は削除してよい。
"""
from sensor import Sensor
from camera import Camera
from mqtt_client import MQTTClient
from s3_uploader import S3Uploader

import util


def build_payload(config, timestamp, values, status, image_keys):
    """
    S3にもMQTTにも送る共通のペイロードを組み立てる

    Args:
        config (dict): config.json の内容
        timestamp (str): 収集時刻（ISO8601）
        values (dict): センサ名 -> 値
        status (dict): センサ名 -> 収集状態（省略可）
        image_keys (list): S3に保存した画像のキー一覧（省略可）

    Notes:
        config由来のメタデータ（区画・株番号・萎れデバイスID）は
        すべてここで組み立てる。呼び出し側で個別に読んで渡さないこと。
    """
    iot_config = config["aws_iot"]

    payload = {
        "deviceID":     config["device_id"],
        "fieldID":      iot_config["field_id"],
        "projectID":    iot_config["project_id"],
        "deviceType":   iot_config.get("device_type", "PiNode"),
        "timestamp":    timestamp,
        # センサ値はトップレベルに展開（DynamoDBでの検索・整合のため）
        **values,
    }
    # 設置場所のメタデータ（区画名・区画内のメロン株番号・株ID）
    payload.update(build_plant_metadata(config))

    if status:
        payload["sensorStatus"] = status
    if image_keys:
        payload["imageKeys"] = image_keys
    # 萎れデバイス未設置のPiNodeでも、キー自体は必ず付けて null を送る
    wilt_device = iot_config.get("wilt_device_id")
    payload["wiltDeviceId"] = wilt_device if wilt_device else None
    return payload


def build_plant_metadata(config):
    """
    config.json の section_id / plant_number からメタデータを組み立てる

    Args:
        config (dict): config.json の内容
    Returns:
        dict: 送信するメタデータ。キーは必ず含み、未設定の項目は null を送る
              例: {"sectionID": "N1W1", "plantNumber": 1, "plantID": "N1W1_1"}
    Notes:
        区画名は温室を3x3に分けた際の「北からの群落番号N + 東からの区画番号W」（例: N1W1）、
        株番号はその区画内で東から数えた番号。両者を繋いだ "N1W1_1" が株IDになる。
    """
    section_id   = config.get("section_id")
    plant_number = config.get("plant_number")

    if not section_id or plant_number is None:
        print("警告: config.json に section_id / plant_number が設定されていません")

    return {
        "sectionID":   section_id if section_id else None,
        "plantNumber": plant_number,
        "plantID":     f"{section_id}_{plant_number}" if section_id and plant_number is not None else None,
    }


if __name__ == "__main__":
    config = util.get_pinode_config()

    # 1. センサーデータ取得 + 収集状態の取得 + CSV保存
    #    （センサ取得を一度だけ行い、値と状態を同時に得る）
    sensor = Sensor()
    df, sensor_timestamp, values, status = sensor.upload_csv_with_status()

    # 2. 画像撮影 + ローカル保存
    saved_paths = Camera().save_images() or []

    # 3. 画像をS3にアップロード
    uploader = S3Uploader()
    s3_keys = uploader.upload_images(saved_paths) if saved_paths else []

    # 4. 送信するペイロードを組み立て
    payload = build_payload(
        config     = config,
        timestamp  = sensor_timestamp,
        values     = values,
        status     = status,
        image_keys = s3_keys if s3_keys else None,
    )

    # 5-A. 【新・本命】センサJSONをS3に直接PUT
    uploader.upload_sensor_json(payload, timestamp=sensor_timestamp)

    # 5-B. 【既存・当面残す】MQTT経由でDynamoDBへ送信
    #      S3と同じペイロードをそのまま流す（メタデータの食い違いを防ぐため）
    #      S3側が安定したら、この行を削除してよい
    MQTTClient().publish_payload(payload)