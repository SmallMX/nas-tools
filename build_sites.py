import os.path
import pickle
from collections.abc import Mapping

from app.helper import IndexerHelper
from config import Config


def to_plain_data(value):
    if isinstance(value, Mapping):
        return {to_plain_data(key): to_plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain_data(item) for item in value]
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str(value)
    return value


if __name__ == "__main__":
    indexers = to_plain_data(IndexerHelper().get_all_indexers())
    output = os.path.join(Config().get_inner_config_path(), "sites.dat")
    with open(output, "wb") as file:
        pickle.dump(indexers, file, pickle.HIGHEST_PROTOCOL)
    print(f"已生成 {output}，共 {len(indexers)} 个站点")
