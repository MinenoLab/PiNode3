import json
from pathlib import Path


def get_pinode_config(config_path="/home/pinode3/config.json"):
    """
    Pinodeの基本情報を取得
    
    Returns:
        pinode_config(json_object): config.jsonに含まれるPinode基礎情報
    
    Notes:
        [config.json](https://github.com/MinenoLab/PiNode3/blob/e3983b7810d5797727f4daf57e4e7f7a659df84a/config.json)

    """
    if Path(config_path).is_file():
        with open(config_path) as f:
            pinode_config = json.load(f)
        return pinode_config
    else:
        raise FileNotFoundError("Config file not found")