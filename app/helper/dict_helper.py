from app.db import MainDb, DbPersist
from app.db.models import SystemDict


class DictHelper:
    
    _db = MainDb()

    @DbPersist(_db)
    def set(self, dtype, key, value, note=""):
        """
        设置字典值
        :param dtype: 字典类型
        :param key: 字典Key
        :param value: 字典值
        :param note: 备注
        :return: True False
        """
        if not dtype or not key or not value:
            return False
        if self.exists(dtype, key):
            return self._db.query(SystemDict).filter(SystemDict.type == dtype,
                                                     SystemDict.key == key).update(
                {
                    "value": value
                }
            )
        else:
            return self._db.insert(SystemDict(
                type=dtype,
                key=key,
                value=value,
                note=note
            ))

    def get(self, dtype, key):
        """
        查询字典值
        :param dtype: 字典类型
        :param key: 字典Key
        :return: 返回字典值
        """
        if not dtype or not key:
            return ""
        ret = self._db.query(SystemDict.value).filter(SystemDict.type == dtype,
                                                      SystemDict.key == key).first()
        if ret:
            return ret[0]
        else:
            return ""

    @DbPersist(_db)
    def delete(self, dtype, key):
        """
        删除字典值
        :param dtype: 字典类型
        :param key: 字典Key
        :return: True False
        """
        if not dtype or not key:
            return False
        return self._db.query(SystemDict).filter(SystemDict.type == dtype,
                                                 SystemDict.key == key).delete()

    def exists(self, dtype, key):
        """
        查询字典是否存在
        :param dtype: 字典类型
        :param key: 字典Key
        :return: True False
        """
        if not dtype or not key:
            return False
        ret = self._db.query(SystemDict).filter(SystemDict.type == dtype,
                                                SystemDict.key == key).count()
        if ret > 0:
            return True
        else:
            return False
