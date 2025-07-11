import os
import subprocess

class USB:
    """
    USBからの情報取得をするためのクラス
    """
    def get(self):
        """
        USB接続されている機器の情報をリストとして一括で取得するメソッド.USB機器が複数接続されている場合は各要素は配列として取得される

        Returns:
            [(self.ports,self.identifys,self.names)] list (int,str,str): ポート番号順に整列

        Attributes:
            self.ports (list[int]) : USB接続している機器のポート番号
            self.identifys (list(str)) : ポート番号に対するデバイス名(SPRESENSE or USB Camera)
            self.names (list[str]): (SPRESENSEの場合)接続ポート番号ごとのデバイスファイルパス
                       (list(int)): (USB Cameraの場合)デバイスID
        """
        self.ports = self._get_connect_ports()
        self.identifys = [self._identify_usb_device(port) for port in self.ports]
        self.names = [
            self._get_spresense_name(port) if identify == 'SPRESENSE' else self._get_usb_camera_name(port)
            for port, identify in zip(self.ports, self.identifys)
        ]
        return list(sorted(zip(self.ports, self.identifys, self.names), key=lambda x: x[0]))

    
    def _get_connect_ports(self):
        """
        接続されているデバイスのUSBポート番号を配列として取得
        
        Returns:
            usb_ports (list[int]): USB接続している機器のポート番号

        Notes:
            配列内の各値は以下の意味を持つ．
            
            # 1 -> USB端子 左上 に接続
            
            # 2 -> USB端子 左下 に接続
            
            # 3 -> USB端子 右上 に接続
            
            # 4 -> USB端子 右下 に接続
        """
        usb_ports = []
        devices = os.listdir('/dev/')
        for device in devices:
            if 'ttyUSB_' in device:
                usb_ports.append(int(device[-1]))
        return usb_ports

    def _identify_usb_device(self, port):
        """
        接続されているUSB機器のデバイス名を取得
        
        Args: 
            port (int): USB接続している機器のポート番号

        Returns:
            'SPRESENSE' (str): ポート番号に対するデバイス名
            'USB Camera' (str): ポート番号に対するデバイス名

        Notes:
            '/dev/ttyUSB_' + USBポート番号 で指定されたパスにシンボリックリンクが存在する
            
            シンボリックリンクの参照物のパス内にttyUSBが含まれていればSPRESENSE,入っていなければUSB Cameraの文字列を返す
        """
        device = '/dev/ttyUSB_' + str(port)
        if 'ttyUSB' in os.readlink(device):
            return 'SPRESENSE'
        else:
            return 'USB Camera'

    def _get_spresense_name(self, port):
        """
        Args:
            port (int): USB接続している機器のポート番号

        Returns:
            SPRESENSEのデバイスファイルへのパス(str)

        """
        return '/dev/ttyUSB_' + str(port)

    def _get_usb_camera_name(self, port):
        """
        USBカメラのデバイスIDを取得.opencvでのカメラキャプチャ等で使用
        
        Args: 
            port (int): USB接続している機器のポート番号

        Returns:
            retVal (int): USBカメラのデバイスID (0 or 1)
        
        Attributes:
            model(str): 接続機器名(Raspberry pi 3 Model B Plus, RasPberry pi 4 Model B等) RasPi3とRasPi4では作成されるシンボリックリンク名が異なるため条件文で検索文字を指定. 接続ポートによっても名称が異なる．
            devices (list[str]): 接続デバイスのシンボリックリンクのパス. シンボリックリンク('/dev/v4l/by-path/?????') -> 機器(path/???1)  に位置する機器の最後の値がデバイスIDとなる
            retval(int): USB接続するとシンボリックリングが2個生成される.2個のうち名前を小さいほうの数字のシンボリックリンク
        
        """

        assert port in [1, 2, 3, 4]
        with open("/proc/cpuinfo", "r") as f:
            model = f.read()
        device_name = ''
        if 'Raspberry Pi 3 Model B Plus' in model:
            if port == 1:
                device_name = '0:1.1.2:1.0-video'
            elif port == 2:
                device_name = '0:1.1.3:1.0-video'
            elif port == 3:
                device_name = '0:1.3:1.0-video'
            elif port == 4:
                device_name = '0:1.2:1.0-video'
            else:
                raise ValueError("unknown port")
        elif 'Raspberry Pi 4 Model B' in model:
            if port == 1:
                device_name = '0:1.3:1.0-video'
            elif port == 2:
                device_name = '0:1.4:1.0-video'
            elif port == 3:
                device_name = '0:1.1:1.0-video'
            elif port == 4:
                device_name = '0:1.2:1.0-video'
            else:
                raise ValueError("unknown port")
        else:
            device_name = '0:1.' + str(port + 1) + ':1.0-video'

        devices = os.listdir('/dev/v4l/by-path')
        for device in devices:
            if device_name in device:
                retVal = int(os.readlink('/dev/v4l/by-path/' + device)[-1])
                if retVal % 2 == 0:
                    return retVal
        raise ValueError("unknown port")