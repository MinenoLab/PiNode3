import cv2
import timeout_decorator
import subprocess
import time
from cobs import cobs
import crcmod
import serial
import datetime as dt
import numpy as np
from pathlib import Path
from usb import USB
import util


class Camera:
    """
    カメラ撮影を行うためのクラス
    """
    def __init__(self):
        self.config = util.get_pinode_config()

    def save_images(self):
        """
        デバイスに応じたカメラ撮影を行うメソッド.ポート番号,PinodeのデバイスID,時刻をファイル名としてSPRESENSEとUSBカメラで撮影した画像を保存する
        
        Attributes:
            devices: (port,identify,name)
            port(int): USB接続している機器のポート番号
            identify(str): ポート番号に対するデバイス名(SPRESENSE or USB Camera)
            name (int): (SPRESENSEの場合)接続ポート番号ごとのデバイスファイルパス
                 (str): (USB Cameraの場合)デバイスID 
                          
        """
        devices = USB().get()
        for port, type, name in devices:
            if type == 'SPRESENSE':
                file_name = "image{:1}/{}_{:02}_HDR_{}.jpg".format(port, self.config['device_id'], port, dt.datetime.now().strftime('%Y%m%d-%H%M'))
                SPRESENSE(name).save(file_name)
            elif type == 'USB Camera':
                file_name = "image{:1}/{}_{:02}_RGB_{}.jpg".format(port, self.config['device_id'], port, dt.datetime.now().strftime('%Y%m%d-%H%M'))
                UsbCamera(name).save(file_name)

class SPRESENSE:
    """
    SPRESENSEに関する設定値,メソッドをまとめたクラス
        
    Args:
        port_num(str): 接続ポート番号ごとのデバイスファイルパス
            
    Notes:
        BAUD_RATE(int): SPRESENSE Main Boardとの通信のためのボーレート
        
        BUFF_SIZE(int): 一回の通信で送られてくるメインデータのデータサイズ（パケットサイズ）
        
        TYPE_INFO(int): SPRESENSEから送られてきたパケットのタイプ(情報データ)
        
        TYPE_IMAGE(int): SPRESENSEから送られてきたパケットのタイプ(画像データ)
        
        TYPE_FINISH(int): SPRESENSEから送られてきたパケットのタイプ(送信終了データ)
        
        TYPE_ERROR(int): SPRESENSEから送られてきたパケットのタイプ(エラーデータ)
    """
    BAUD_RATE   = 115200  
    TYPE_INFO   = 0
    TYPE_IMAGE  = 1
    TYPE_FINISH = 2
    TYPE_ERROR  = 3

    def __init__(self, port_num):
        self.port_num = port_num
        self.config = util.get_pinode_config()

    def save(self, file_name):
        """
        SPRESENSEから受け取ったバイナリ画像を保存する
        
        Args:
            file_name (str): 保存するファイル名
        
        Returns:
            ret (bool) : 画像保存が成功したか

        Notes:
            ・3回実行を行いエラーが発生した場合は終了する
            
            ・シリアル通信の接続に時間がかかるため2秒間sleep
            
            ・エラーが発生した場合再起動

        """
        local_file_path = str(Path(self.config['camera']['image_dir']) / Path(file_name))

        
        for i in range(3):
            try:
                with serial.Serial(self.port_num, self.BAUD_RATE, timeout = 3) as ser:
                    time.sleep(2)
                    img = self._get_image_data(ser)
                    print(f"save image : {local_file_path}")
                    with open(local_file_path, "wb") as f:
                        f.write(img)
                return True
            except Exception as e:
                print(e)
                self._reboot()
        print("failed to get image")
        return False

    def _reboot(self):
        """Function
        USB機器の電源供給を一度切り再び入れる
        """
        subprocess.call("sudo sh -c \"echo -n \"1-1\" > /sys/bus/usb/drivers/usb/unbind\"", shell=True)
        time.sleep(1)
        subprocess.call("sudo sh -c \"echo -n \"1-1\" > /sys/bus/usb/drivers/usb/bind\"", shell=True)
        time.sleep(5)

    def _get_packet(self, ser, timeout=3):
        """Function
        接続しているシリアルポートから1パケット分データの受信を行う
        
        Args:
            ser (serial.Serial): 接続しているシリアル
            timeout (uint)     : タイムアウト時間（sec）

        Returns:
            [is_crc_valid, decoded[0],index,decoded[5:]] :list (bool, int,int,bytearray)
            
        Attributes:
            is_crc_valid: CRCチェックの結果
            index (int): decodedは最初の4桁がインデックス番号.4桁の数値をint型に変換し画像インデックスとして使用
            decoded[0] (int): SPRESENSEから送られてきたパケットのタイプ(画像データ)
            decoded[5:](bytearray): 画像データ本体

        Notes:
            1バイトずつシリアル通信で画像を取得しパケット終了文字x00が来るまでデータを受け取る. その後,cobs.decodeで終了文字列を画像に対応するものに戻す

            [参考]シリアル通信で受け取る正常な画像データは以下のような構造を持つ
                
                decoded[0]:TYPE_IMAGE(int: 1)

                decoded[1]:index 4桁目
            
                decoded[2]:index 3桁目

                decoded[3]:index 2桁目
            
                decoded[4]:index 1桁目
            
                decoded[5]:画像データ内容1
            
                decoded[6]:画像データ内容2
                
                ...
                
                decoded[X]:画像データ内容X
                CRC       :データのCRC(8bit)
    
        """
        buf = bytearray()
        start = time.time()
        while True:
            val = ser.read()
            if val == b'\x00':
                break
            elif time.time() - start > timeout:
                return False, self.TYPE_ERROR, None, None
            buf += val
        decoded = cobs.decode(buf)

        crc8_func = crcmod.predefined.mkCrcFun('crc-8maxim')
        crc = crc8_func(decoded[0:-1])
        is_crc_valid = (crc == decoded[-1])
        packet_type = decoded[0]
        index = int(decoded[1]) * 1000 + int(decoded[2]) * 100 + int(decoded[3]) * 10 + int(decoded[4])
        payload = decoded[5:-1]
        return is_crc_valid, packet_type, index, payload

    def _send_request_image(self, ser):
        """
        画像の送信を要求するパケットをSPRESENSEに送信する
        
        Args:
            ser (serial.Serial): 接続しているシリアル
        
        Notes:
            ”S” がSPRESENSEに送信されると画像撮影が行われる
        """
        ser.write(str.encode('S\n'))

    def _send_complete_image(self, ser):
        """
        画像データをすべて受信したことを伝えるパケットをSPRESENSEに送信する
        
        Args:
            ser (serial.Serial): 接続しているシリアル
        
        Notes:
            SPRESENSEの待機状態を解除
        """
        ser.write(str.encode('E\n'))

    def _send_request_resend(self, ser, index):
        """
        画像の再送を要求するパケットをSPRESENSEに送信する
        
        Args:
            ser (serial.Serial): 接続しているシリアル
            index (int): 再送するインデックス番号
        
        Notes:
            "R"+index番号をSPRESENSEに送信するとインデックス番号に対応するデータを再送してくれる
        
        """
        ser.write(str.encode(f'R{index}\n'))

    @timeout_decorator.timeout(50, use_signals=False)
    def _get_image_data(self, ser):
        """
        SPRESENSEから画像データを受け取り,バイナリの画像データを作成する.通信時間が50秒を超えた場合タイムアウト

        Args:
            ser (serial.Serial): 接続しているシリアル

        Returns:
            jgp_data (bytearray): 画像データ（JPEGバイナリ）
            
        Attributes:
            img (bytearray): 送信されたバイナリ画像データ.  size = 最大index値 * BUFF_SIZE(100)
            resend_index_list (list[int]): 再送してほしいインデックスのリスト
            finish_flag (list[bool]): データ受信完了時にSPRESENSEに終了信号を送信するために使用
            send_flg (list[bool]): 正常に受信できたかを管理するリスト,すべてFalseとして初期化され,正常受信でTrueに変更
        
        Notes:
            各信号とその信号を受け取った際の実施事項
                
                TYPE_INFO: 画像が撮影時に一番最初に送られる信号
                    この信号を受け取った後,以下の要素を初期化: img,max_index,sendflg
                
                TYPE_IMAGE: データが画像であった場合に送られる信号
                    正常な受信が行われたため,imgにデータを追加し,send_flgを書き換える
                
                TYPE_FINISH: 最後の画像データの場合に送られる信号
                    正常な受信が行われたため,imgにデータを追加し,finish_flgを書き換える
                
                TYPE_ERROR: データ受信に問題があった場合に送られる信号
        
            finish_flagがTrueの場合: send_flagがFalseであるもの,resend_index_listに含まれているものに対して再送命令. 
            すべてのデータが完全に送られるまでWhile分のループを実行
        """
        # 1. 送信要求
        self._send_request_image(ser)

        # 2. INFOパケット待ち
        ret, code, index, data = self._get_packet(ser)
        if ret and (code == self.TYPE_INFO):
            max_index = index
            buf = [None] * (max_index + 1)
        else:
            raise ValueError("INFOパケット受信できません")

        # 3. 画像データ受信
        for i in range(len(buf)):
            ret, code, index, data = self._get_packet(ser)
            if ret:
                if (code == self.TYPE_IMAGE) or (code == self.TYPE_FINISH):
                    buf[index] = data

        # 4. 再送要求（１回まで）
        for i in range(len(buf)):
            if buf[i] is None:
                self._send_request_resend(ser, i)
                ret, code, index, data = self._get_packet(ser)
                if ret:
                    if (code == self.TYPE_IMAGE) or (code == self.TYPE_FINISH):
                        buf[index] = data

        # 5. 終了送信
        self._send_complete_image(ser)

        jpg_data = bytearray(b''.join(buf))
        return jpg_data

class UsbCamera:
    """
    USBカメラで撮影した写真保存のためのクラス
    
    Args:
        device_name (int): デバイスID(カメラインデックス)
    """
    def __init__(self, device_name):
        
        self.config = util.get_pinode_config()
        self.device_name = device_name
    
    @timeout_decorator.timeout(20)
    def save(self, file_name):
        """
        USBカメラで撮影した写真の保存. 20秒のタイムアウト設定

        Args:
            filename (str): 保存ファイル名
        
        Returns:
            ret(bool) : 画像保存が成功したか

        Notes:
            カメラ読み込みを50回実行
                (理由)撮影が始まってすぐの段階ではカメラ補正がうまく働かず適切な写真を取得できない.
                回数を繰り返すことで適切な画像取得が可能. (Timeoutも試したがうまく動作せず)
        """
        cap = cv2.VideoCapture(self.device_name, cv2.CAP_V4L)
        for _ in range(50):
            ret, frame = cap.read()
        if not ret:
            return False

        local_file_path = str(Path(self.config['camera']['image_dir']) / Path(file_name))
        print(f"save image : {local_file_path}")
        cv2.imwrite(local_file_path, frame)
        return True


if __name__ == '__main__':
    while True:
        devices = USB().get()
        print(devices)
        for i, (port, type, name) in enumerate(devices):
            print(port, type, name)
            tm = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            if type == 'SPRESENSE':
                SPRESENSE(name).save(f"test_{port}_{tm}.jpg")
            elif type == 'USB Camera':
                UsbCamera(name).save(f"test_{port}_{tm}.jpg")
        time.sleep(60*10)

