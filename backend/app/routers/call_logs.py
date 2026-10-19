"""调用日志路由：历史「调用过程」记录查询（设置页回看）。

数据由 services/process.py 在事件产出时旁路写入 services/call_log_store.py：
每次生成流程一条记录，含 llm_start / delta（已合并）/ llm_done / tool / step 全量事件。
"""
from fastapi import APIRouter, HTTPException

from ..services import call_log_store

router = APIRouter(prefix="/api/call-logs", tags=["call-logs"])


@router.get("")
async def list_call_logs(limit: int = 50, offset: int = 0, q: str = ""):
    """调用记录列表（新→旧，不含 events）；q 大小写不敏感匹配 flow + purpose。"""
    return {"entries": await call_log_store.list_records(limit=limit, offset=offset, q=q)}


@router.get("/{record_id}")
async def get_call_log(record_id: str):
    """单条调用记录详情（含完整 events）。"""
    rec = await call_log_store.get_record(record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="调用记录不存在")
    return rec
