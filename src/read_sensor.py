import atexit
from gpiozero import LED, Button, DigitalOutputDevice
import time
from smbus2 import SMBus
import board
import busio
import spidev


# GPIOの定義
GPIO_LED = 18    # LED_G
GPIO_DSW = [12, 16, 20, 21]    # SW1_1, SW1_2, SW1_3, SW1_4
GPIO_I2C_EN = [4, 5, 6, 13, 19]    # I2C Enable Pins
GPIO_SPI_OE = 25    # SPI Output Enable

# I2Cアドレスの定義
SHT25_ADDR = 0x40      # SHT25センサのアドレス
S1133_INT_ADDR = 0x30  # S1133内部照度センサのアドレス
S1133_EXT_ADDR = 0x31  # S1133外部照度センサのアドレス

class SensorManager:
    def __init__(self):
        # デバイスの初期化
        self.led = LED(GPIO_LED)
        # self.dsw_buttons = [Button(pin, pull_up=False) for pin in GPIO_DSW]
        self.i2c_enables = [DigitalOutputDevice(pin) for pin in GPIO_I2C_EN]
        self.spi_enable = DigitalOutputDevice(GPIO_SPI_OE)
        self.d1tbl = [0x00, 0x40, 0x80, 0xC0]       # send data 1
        self.spi = spidev.SpiDev()
        
        # クリーンアップの登録
        atexit.register(self.cleanup)

    def cleanup(self):
        """全てのデバイスをクリーンアップ"""
        self.led.close()
        # for btn in self.dsw_buttons:
        #     btn.close()
        for dev in self.i2c_enables:
            dev.close()
        self.spi_enable.close()

    def led_toggle(self):
        """LEDの切り替え"""
        self.led.toggle()

    # def dsw_read(self):
    #     """ DIPスイッチの状態を取得 """
    #     return sum((~btn.value & 1) << i for i, btn in enumerate(self.dsw_buttons))

    def s1133_read(self, addr):
        """ 照度センサ（S1133）を読み取る """
        # I2Cイネーブルピンの制御
        for enable in self.i2c_enables:
            enable.off()
        time.sleep(0.1)

        try:
            # I2Cバスの初期化
            i2c = busio.I2C(board.SCL, board.SDA)
            
            # データの読み取り
            data = bytearray(3)
            i2c.readfrom_into(addr, data)

            val = ((data[0] & 0xff) << 4) | ((data[1] & 0xf0) >> 4)
            rng = (data[1] & 0x0c) >> 2
            div = (1, 1, 4, 16)

            result = int(val / 4096 * 250000 / div[rng])
        except Exception as e:
            print(f"I2C Error: {e}")
            result = 0
        finally:
            # I2Cイネーブルピンを元に戻す
            for enable in self.i2c_enables:
                enable.on()

        return result

    def sht25_read(self):
        """ 温度・湿度センサ（SHT25）を読み取る """
        # I2Cイネーブルピンの制御
        for enable in self.i2c_enables:
            enable.off()

        try:
            # I2Cバスの初期化
            i2c = busio.I2C(board.SCL, board.SDA)
            
            # 温度測定
            i2c.writeto(SHT25_ADDR, bytes([0xE3]))
            temp_data = bytearray(3)
            i2c.readfrom_into(SHT25_ADDR, temp_data)

            # 湿度測定
            i2c.writeto(SHT25_ADDR, bytes([0xE5]))
            humi_data = bytearray(3)
            i2c.readfrom_into(SHT25_ADDR, humi_data)

            # 計算
            nT = (temp_data[0] << 8 | temp_data[1] & 0xFC)
            nH = (humi_data[0] << 8 | humi_data[1] & 0xFC)

            fT = -46.85 + 175.72 * (nT / 65536)
            fH = -6.00 + 125.00 * (nH / 65536)

        except Exception as e:
            print(f"I2C Error: {e}")
            fT, fH = 0, 0
        finally:
            # I2Cイネーブルピンを元に戻す
            for enable in self.i2c_enables:
                enable.on()

        return fT, fH

    def stem_fruit_read(self):
        """茎径＆果実径センサを読み取る（出力：V）"""
        self.spi_enable.on()
        time.sleep(0.1)

        try:
            self.spi.open(0, 0) # bus0, CE0
            self.spi.max_speed_hz = 1000000  # 1MHz

            # STEM(Ch0)を読み取る
            rd = self.spi.xfer2([0x06, self.d1tbl[0], 0x00])
            v = (rd[1] & 0x1f) * 256 + rd[2]
            v = v / 4095 * 2.048
            stem_v = round(v, 2)

            # FRUIT(Ch1)を読み取る
            rd = self.spi.xfer2([0x06, self.d1tbl[1], 0x00])
            v = (rd[1] & 0x1f) * 256 + rd[2]
            v = v / 4095 * 2.048
            fruit_v = round(v, 2)
        except Exception as e:
            print(f"SPI Error: {e}")
            stem_v = 0
            fruit_v = 0
        finally:
            self.spi.close()

        self.spi_enable.off()
               
        return (stem_v, fruit_v)

    def get(self, sensor):
        """ センサーデータを取得 """
        sensor_map = {
            # "dsw": self.dsw_read,
            "i_v_light": lambda: self.s1133_read(S1133_INT_ADDR),
            "u_v_light": lambda: self.s1133_read(S1133_EXT_ADDR),
            "temperature": lambda: self.sht25_read()[0],
            "humidity": lambda: self.sht25_read()[1],
            "temperature_hq": lambda: 0,
            "humidity_hq": lambda: 0,
            "stem": lambda: self.stem_fruit_read()[0],
            "fruit_diagram": lambda: self.stem_fruit_read()[1]
        }

        if sensor in sensor_map:
            return sensor_map[sensor]()
        
        print(f"Unknown sensor: {sensor}")
        return None

def main():
    sensor_manager = SensorManager()
    
    try:
        while True:
            # print(f"スイッチ: {sensor_manager.get('dsw'):04b}")
            print(f"温度: {sensor_manager.get('temperature'):.2f} °C")
            print(f"湿度: {sensor_manager.get('humidity'):.2f} %")
            print(f"内部照度: {sensor_manager.get('i_v_light')} lux")
            print(f"外部照度: {sensor_manager.get('u_v_light')} lux")
            print(f"茎径: {sensor_manager.get('stem')} V")
            print(f"果実径: {sensor_manager.get('fruit_diagram')} V")
            print("--------------------------")
            time.sleep(1)
    except KeyboardInterrupt:
        print("プログラム終了")

if __name__ == "__main__":
    main()