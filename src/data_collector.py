from sensor import Sensor
from camera import Camera

if __name__ == "__main__":
    Sensor().upload_csv()
    Camera().save_images()