"""高亮标注路由：读者的想法/认知默认高亮，颜色与方式可在设置中调整。"""
from fastapi import APIRouter, HTTPException, Query

from ..schemas import AnnotationCreate, AnnotationUpdate
from ..services import annotations_store

router = APIRouter(prefix="/api", tags=["annotations"])


@router.get("/annotations")
def list_annotations(path: str = Query(...)):
    return {"annotations": annotations_store.list_annotations(path)}


@router.post("/annotations")
def add_annotation(body: AnnotationCreate):
    if not annotations_store.note_exists(body.path):
        raise HTTPException(status_code=404, detail=f"笔记不存在：{body.path}")
    return annotations_store.add_annotation(
        body.path,
        quote=body.quote,
        prefix=body.prefix,
        suffix=body.suffix,
        occurrence=body.occurrence,
        color=body.color,
        style=body.style,
        comment=body.comment,
    )


@router.put("/annotations/{ann_id}")
def update_annotation(ann_id: str, body: AnnotationUpdate, path: str = Query(...)):
    return annotations_store.update_annotation(
        path, ann_id, body.model_dump(exclude_none=True)
    )


@router.delete("/annotations/{ann_id}")
def delete_annotation(ann_id: str, path: str = Query(...)):
    annotations_store.delete_annotation(path, ann_id)
    return {"ok": True}
