"""pytest 共享夹具：把数据目录指向临时目录，隔离真实数据。"""
import pytest


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEBOOK_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"
