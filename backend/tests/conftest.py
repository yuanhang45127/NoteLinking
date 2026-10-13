"""pytest 共享夹具：把数据目录指向临时目录，隔离真实数据。"""
import pytest

from app.services import auth_service, mail_service


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEBOOK_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture(autouse=True)
def _clean_rate_state():
    """限流与验证码状态是模块级内存，测试前清空避免互相污染。"""
    auth_service.reset_rate_limits()
    mail_service.clear_code("u1@x.com")
    mail_service._store.clear()
    yield
    auth_service.reset_rate_limits()
    mail_service._store.clear()
