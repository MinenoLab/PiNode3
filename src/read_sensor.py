from gpiozero import LED, Button, DigitalOutputDevice, MCP3204
from smbus2 import SMBus, i2c_msg
import atexit
import time

# GPIOの定義
GPIO_LED = 18                    # LED_G
GPIO_DSW = [12, 16, 20, 21]      # SW1_1, SW1_2, SW1_3, SW1_4
GPIO_I2C_EN = [4, 5, 6, 13, 19]  # I2C Enable Pins
GPIO_SPI_OE = 25                 # SPI Output Enable

# I2Cアドレスの定義
SHT25_ADDR = 0x40      # SHT25センサのアドレス
S1133_INT_ADDR = 0x30  # S1133内部照度センサのアドレス
S1133_EXT_ADDR = 0x31  # S1133外部照度センサのアドレス
SHT85_ADDR = 0x44      # SHT85センサのアドレス

MCP3204_REFV = 2.048   # MCP3204リファレンス電圧


class SensorManager:
    def __init__(self):
        # デバイスの初期化
        self.led = LED(GPIO_LED)
        self.dip = [Button(pin, pull_up=False) for pin in GPIO_DSW]
        self.i2c_enables = [DigitalOutputDevice(pin) for pin in GPIO_I2C_EN]
        self.spi_enable = DigitalOutputDevice(GPIO_SPI_OE)
        self.adc_stem = MCP3204(0, max_voltage=MCP3204_REFV)
        self.adc_fruit = MCP3204(1, max_voltage=MCP3204_REFV)
        # クリーンアップの登録
        atexit.register(self.cleanup)

    def cleanup(self):
        """全てのデバイスをクリーンアップ"""
        self.led.close()
        for sw in self.dip:
            sw.close()
        for en in self.i2c_enables:
            en.close()
        self.spi_enable.close()
        self.adc_stem.close()
        self.adc_fruit.close()

    def toggle_led(self):
        """LEDの切り替え"""
        self.led.toggle()

    @property
    def inner_lx(self):
        """内部照度(lx)"""
        self.i2c_enables[1].off()
        lx = self._s1133_read(S1133_INT_ADDR)
        self.i2c_enables[1].on()
        return lx

    @property
    def outer_lx(self):
        """外部照度(lx)"""
        self.i2c_enables[2].off()
        lx = self._s1133_read(S1133_EXT_ADDR)
        self.i2c_enables[2].on()
        return lx

    @property
    def temperature(self):
        """気温(℃)"""
        self.i2c_enables[0].off()
        temp = self._sht25_read()[0]
        self.i2c_enables[0].off()
        return temp

    @property
    def humidity(self):
        """相対湿度(RH%)"""
        self.i2c_enables[0].off()
        humi = self._sht25_read()[1]
        self.i2c_enables[0].on()
        return humi

    @property
    def stem(self):
        """茎径：センサの電圧(0～2.048V)を返す"""
        self.spi_enable.on()
        value = self.adc_stem.value * MCP3204_REFV
        self.spi_enable.off()
        return value

    @property
    def fruit_diameter(self):
        """果実径：センサの電圧(0～2.048V)を返す"""
        self.spi_enable.on()
        value = self.adc_fruit.value * MCP3204_REFV
        self.spi_enable.off()
        return value

    @property
    def is_on_dip1(self):
        """DIPスイッチ1がONか"""
        return not self.dip[0].is_pressed

    @property
    def is_on_dip2(self):
        """DIPスイッチ2がONか"""
        return not self.dip[1].is_pressed

    @property
    def is_on_dip3(self):
        """DIPスイッチ3がONか"""
        return not self.dip[2].is_pressed

    @property
    def is_on_dip4(self):
        """DIPスイッチ4がONか"""
        return not self.dip[3].is_pressed

    @property
    def opt_temperature(self):
        """強制通風筒（オプション）の気温(℃)"""
        self.i2c_enables[4].off()
        temp = self._sht85_read()[0]
        self.i2c_enables[4].on()
        return temp

    @property
    def opt_humidity(self):
        """強制通風筒（オプション）の湿度(RH%)"""
        self.i2c_enables[4].off()
        humi = self._sht85_read()[1]
        self.i2c_enables[4].on()
        return humi

    def _s1133_read(self, addr):
        """ 照度センサ（S1133）を読み取る """
        try:
            with SMBus(1) as bus:
                # データの読み取り
                read = i2c_msg.read(addr, 3)
                bus.i2c_rdwr(read)
                data = list(read)
            val = ((data[0] & 0xff) << 4) | ((data[1] & 0xf0) >> 4)
            rng = (data[1] & 0x0c) >> 2
            div = (1, 1, 4, 16)

            result = int(val / 4096 * 250000 / div[rng])
        except Exception as e:
            print(f"I2C Error: {e}")
            result = 0
        return result

    def _sht25_read(self):
        """ 温度・湿度センサ（SHT25）を読み取る """
        try:
            # I2Cバスの初期化
            with SMBus(1) as bus:
                # 温度測定
                temp_data = bus.read_i2c_block_data(SHT25_ADDR, 0xE3, 3)

                # 湿度測定
                humi_data = bus.read_i2c_block_data(SHT25_ADDR, 0xE5, 3)
            # 計算
            nT = (temp_data[0] << 8 | temp_data[1] & 0xFC)
            nH = (humi_data[0] << 8 | humi_data[1] & 0xFC)

            fT = -46.85 + 175.72 * (nT / 65535.0)
            fH = - 6.00 + 125.00 * (nH / 65535.0)
        except Exception as e:
            print(f"I2C Error: {e}")
            fT, fH = 0.0, 0.0
        return fT, fH


    def _sht85_read(self):
        """ 温度・湿度センサ（SHT85）を読み取る """
        try:
            # I2Cバスの初期化
            with SMBus(1) as bus:
                # 測定
                write = i2c_msg.write(SHT85_ADDR, [0x24, 0x00])
                bus.i2c_rdwr(write)
                time.sleep(0.1)
                read = i2c_msg.read(SHT85_ADDR, 6)
                bus.i2c_rdwr(read)
                data = list(read)

            # 計算
            nT = (data[0] << 8 | data[1] << 0)
            nH = (data[3] << 8 | data[4] << 0)

            fT = -45.00 + 175.00 * (nT / 65535.0)
            fH =   0.00 + 100.00 * (nH / 65535.0)
        except Exception as e:
            print(f"I2C Error: {e}")
            fT, fH = 0.0, 0.0
        return fT, fH

if __name__ == "__main__":
    sm = SensorManager()
    
    try:
        while True:
            sm.toggle_led()
            print(f"DIP-SW   : {sm.is_on_dip1}-{sm.is_on_dip2}-{sm.is_on_dip3}-{sm.is_on_dip4}")
            print(f"温度     : {sm.temperature:.2f} ℃")
            print(f"湿度     : {sm.humidity:.2f} %")
            print(f"内部照度 : {sm.inner_lx} lux")
            print(f"外部照度 : {sm.outer_lx} lux")
            print(f"茎径     : {sm.stem} V")
            print(f"果実径   : {sm.fruit_diameter} V")
            print(f"OPT気温  : {sm.opt_temperature:.2f} ℃")
            print(f"OPT湿度  : {sm.opt_humidity:.2f} %")
            print("--------------------------")
            time.sleep(1)
    except KeyboardInterrupt:
        print("プログラム終了")

