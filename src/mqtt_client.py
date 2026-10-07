"""
AWS IoT Core への MQTT 送信クライアント（awsiotsdk v2 対応）
config.json の設定を使用する
"""
from awscrt import mqtt
from awsiot import mqtt_connection_builder
from pathlib import Path
import json
import util


class MQTTClient:
    """
    AWS IoT Core への MQTT 送信クライアント

    Notes:
        接続に必要な設定だけをconfig.jsonから読む。
        送信内容（fieldID・projectID等）はペイロード側の責任なので、
        このクラスでは持たない。

        config.json に以下の設定が必要:
        {
            "device_id": "PiNode36",
            "aws_iot": {
                "endpoint": "xxxx.iot.ap-northeast-1.amazonaws.com",
                "cert_dir": "/etc/iot"
            }
        }
    """
    def __init__(self):
        config     = util.get_pinode_config()
        iot_config = config["aws_iot"]

        self.device_id = config["device_id"]
        self.topic     = f"agri/sensors/{self.device_id}/data"

        cert_dir = Path(iot_config["cert_dir"])

        # MQTT接続を構築（MTLSで証明書認証）
        self._connection = mqtt_connection_builder.mtls_from_path(
            endpoint         = iot_config["endpoint"],
            cert_filepath    = str(cert_dir / "cert.pem"),
            pri_key_filepath = str(cert_dir / "private.key"),
            ca_filepath      = str(cert_dir / "root-CA.pem"),
            client_id        = self.device_id,
            clean_session    = False,
            keep_alive_secs  = 30,
        )

    def publish_payload(self, payload: dict):
        """
        組み立て済みのペイロードをそのまま MQTT で送信する

        Args:
            payload (dict): 送信するペイロード。data_collector.build_payload() で組み立てる

        Notes:
            - このクラスはペイロードを組み立てない。S3に送るJSONと全く同じ辞書を
              受け取って流すだけにする。（区画名・メロン株番号・萎れデバイスIDなどの
              メタデータを2箇所で組み立てて食い違うのを防ぐため）
            - センサ値(temperature等)はトップレベルに展開されている。
              → DynamoDBで各値が独立カラムになり、検索・フィルタしやすい。
            - 収集状態(sensorStatus)は1つのMapにまとまっている。
              → 検索対象ではなく付随情報のため、カラムを増やさない。
            - PK: deviceID / SK: timestamp はトップレベルに置く。
        """
        connected = False
        try:
            # 接続
            connect_future = self._connection.connect()
            connect_future.result()
            connected = True

            # 送信
            publish_future, _ = self._connection.publish(
                topic   = self.topic,
                payload = json.dumps(payload),
                qos     = mqtt.QoS.AT_LEAST_ONCE,
            )
            publish_future.result()
            print(f"MQTT送信完了: {payload['timestamp']}")

        except Exception as e:
            print(f"MQTT送信エラー: {e}")

        finally:
            # 接続済みの場合のみ切断
            # 未接続時にdisconnectを呼ぶとクラッシュするため必ずフラグで判定する
            if connected:
                try:
                    disconnect_future = self._connection.disconnect()
                    disconnect_future.result()
                except Exception:
                    pass