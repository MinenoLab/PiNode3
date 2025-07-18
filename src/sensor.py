import json
import time
import pandas as pd
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone
import read_sensor
import util
from db import InfluxDB


class SensorResult(Enum):
    """
    センサデータの状態を表す列挙型

    Notes:
        SUCCESS             = 0  : 正常
        EMPTY_STRING_ERROR  = 1  : 空文字エラー
        NAN_ERROR           = 2  : nanエラー
        INF_ERROR           = 3  : infエラー
        MIN_VALUE_ERROR     = 4  : 最小値エラー
        MAX_VALUE_ERROR     = 5  : 最大値エラー
    """
    SUCCESS             = 0  
    EMPTY_STRING_ERROR  = 1  
    NAN_ERROR           = 2  
    INF_ERROR           = 3  
    MIN_VALUE_ERROR     = 4  
    MAX_VALUE_ERROR     = 5  


class Sensor:
    """
    センサからの情報取得を行うクラス
    """
    # センサ名
    TEMP   = "temperature"
    HD     = "humidity"
    I_LX   = "i_v_light"
    U_LX   = "u_v_light"
    TEMPHQ = "temperature_hq"
    HDHQ   = "humidity_hq"
    STEM   = "stem"
    FRUIT  = "fruit_diagram"

    def __init__(self):
        """
        センサクラスの初期化メソッド

        Notes:
            設定ファイルと前回のセンサデータを読み込む
        """
        # 設定ファイルの読み込み
        self.config = util.get_pinode_config()
        # 前回のセンサデータパス
        self.previous_data_path = self.config['sensor']['previous_data_path']
        self.sensor_manager = read_sensor.SensorManager()
        
        # 前回のセンサデータを読み込む
        with open(self.previous_data_path, "r") as f:
            self.previous_sensor_data = json.load(f)

        # センサと取得メソッドの対応
        self.sensors = {
            Sensor.TEMP    : self.sensor_manager.temperature,
            Sensor.HD      : self.sensor_manager.humidity,
            Sensor.I_LX    : self.sensor_manager.inner_lx,
            Sensor.U_LX    : self.sensor_manager.outer_lx,
            Sensor.TEMPHQ  : self.sensor_manager.opt_temperature,
            Sensor.HDHQ    : self.sensor_manager.opt_humidity,
            Sensor.STEM    : self.sensor_manager.stem,
            Sensor.FRUIT   : self.sensor_manager.fruit_diameter,
        }
 
    def get(self, sensor_name : str):
        """
        指定されたセンサのデータを取得するメソッド
        
        Args:
            sensor_name(str): センサ名
        
        Returns: 
            result(SensorResult): センサデータの状態
            data(float): センサデータ
        
        Notes:
            指定された回数だけデータ取得を試み、
            正常に取得できない場合は前回の値を返す
        """
        result = SensorResult.EMPTY_STRING_ERROR
        max_retry = self.config['sensor']['max_retry_count'].get(sensor_name, 3)

        for _ in range(max_retry):
            try:
                # センサデータの取得
                data = float(self.sensors[sensor_name])
                # 取得後の待機時間
                time.sleep(self.config['sensor']['sleep_time'].get(sensor_name, 0.1))
                # データの妥当性検証
                result = self._is_valid(data, sensor_name)
                # データが正常な場合
                if result == SensorResult.SUCCESS:
                    # 前回のセンサデータを更新
                    with open(self.previous_data_path, 'w') as f:
                        self.previous_sensor_data[sensor_name] = data
                        json.dump(self.previous_sensor_data, f, indent=4)
                    return result, data
            except Exception as e:
                print(f"センサ取得エラー ({sensor_name}): {e}")
            finally:
                # リトライ間隔
                time.sleep(self.config['sensor']['retry_interval'].get(sensor_name, 0.5))
        # すべてのリトライに失敗した場合、前回の値を返す
        return result, self.previous_sensor_data[sensor_name]

    def upload_csv(self):
        """
        センサデータを取得し、InfluxDBにアップロードまたはCSVに保存するメソッド

        Returns:
            df(pd.DataFrame): アップロードしたデータ

        Notes:
            全センサのデータを取得
            データの取得に失敗した場合はCSVにデータを保存
        """
        # センサデータの取得
        df = pd.DataFrame(
            data  = {sensor_name : self.get(sensor_name)[1] for sensor_name in self.sensors.keys()},
            index = [datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')]
        )

        try:
            # InfluxDBにデータをアップロード
            InfluxDB().upload_dataframe(df)
        except Exception as e:
            print(f"InfluxDBアップロードエラー: {e}")
        finally:
            csv_path = Path(self.config['sensor']['csv_dir']) / f"{self.config['device_id']}_{datetime.now().strftime('%Y%m%d-%H%M.csv')}"
            df.to_csv(csv_path)
        return df

    def _is_valid(self, data, sensor:str):
        """
        センサデータの妥当性を検証するメソッド
        
        Args:
            data(int|float): センサデータ
            sensor(str): センサ名
        
        Returns:
            SensorResult: データの状態
        """
        # データが空の場合
        if not data:  
            return SensorResult.EMPTY_STRING_ERROR
        # NaNの場合
        if data == 'nan':  
            return SensorResult.NAN_ERROR
        # 無限大の場合
        if data == 'inf': 
            return SensorResult.INF_ERROR
        # 最小値チェック
        min_value = self.config['sensor']['min_value'].get(sensor, float('-inf'))
        if float(data) < min_value:  
            return SensorResult.MIN_VALUE_ERROR
        # 最大値チェック
        max_value = self.config['sensor']['max_value'].get(sensor, float('inf'))
        if float(data) > max_value: 
            return SensorResult.MAX_VALUE_ERROR
        # すべてのチェックを通過
        return SensorResult.SUCCESS


if __name__ == "__main__":
    sensor = Sensor()
    df = sensor.upload_csv()
    print(df)

