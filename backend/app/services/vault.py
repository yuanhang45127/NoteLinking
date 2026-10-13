"""笔记库服务：主题（顶层文件夹）、笔记（md 文件）、目录树、搜索、反链。

库内约定：
- 主题 = vault 下的顶层文件夹，可多层嵌套；主题的 emoji 图标存在
  文件夹内隐藏文件 .nl-topic.json（随主题重命名自动保留）；
- 笔记 = 任意 .md 文件；
- 词条解释文档 = 主题根下 terms/ 文件夹内的 md（frontmatter type: term）。
"""
import datetime
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException

from ..config import get_vault_dir
from ..markdown_utils import build_frontmatter, extract_wiki_links, parse_frontmatter
from ..utils import resolve_in, safe_rel_parts, sanitize_filename, unique_path


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _iter_md(root: Path) -> List[Path]:
    if not root.exists():
        return []
    out = []
    for p in root.rglob("*.md"):
        # 只看相对 root 的路径段，避免把上级目录里的 .xxx（如工作区名）误判为隐藏目录
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        out.append(p)
    return sorted(out)


def note_id(rel: str) -> str:
    """库内标识：相对路径去掉 .md 后缀，posix 风格。"""
    name = str(safe_rel_parts(rel))
    return name[: -3] if name.lower().endswith(".md") else name


# ---------------------------------------------------------------- 主题
def list_topics() -> List[Dict]:
    vault = get_vault_dir()
    topics = []
    for p in sorted(vault.iterdir()):
        if p.is_dir() and not p.name.startswith("."):
            notes = _iter_md(p)
            topics.append(
                {
                    "name": p.name,
                    "path": p.name,
                    "emoji": get_topic_emoji(p.name),
                    "note_count": len(notes),
                    "term_count": sum(1 for n in notes if n.parent.name == "terms"),
                    "updated_at": _max_mtime(notes, p),
                }
            )
    return topics


def _max_mtime(notes: List[Path], fallback: Path) -> str:
    srcs = notes + [fallback]
    ts = max((s.stat().st_mtime for s in srcs if s.exists()), default=0)
    return datetime.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def create_topic(name: str) -> Dict:
    vault = get_vault_dir()
    clean = sanitize_filename(name, "新主题")
    target = vault / clean
    if target.exists():
        raise HTTPException(status_code=409, detail=f"主题已存在：{clean}")
    target.mkdir(parents=True)
    return {"name": clean, "path": clean}


def delete_topic(name: str, recursive: bool = False) -> None:
    vault = get_vault_dir()
    target = resolve_in(vault, name)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail=f"主题不存在：{name}")
    if not recursive and any(target.rglob("*.md")):
        raise HTTPException(status_code=400, detail="主题下仍有笔记；如确认删除请传 recursive=true")
    shutil.rmtree(target)


def rename_topic(old: str, new: str) -> Dict:
    vault = get_vault_dir()
    src = resolve_in(vault, old)
    if not src.is_dir():
        raise HTTPException(status_code=404, detail=f"主题不存在：{old}")
    dst = vault / sanitize_filename(new, old)
    if dst.exists():
        raise HTTPException(status_code=409, detail=f"目标主题已存在：{dst.name}")
    src.rename(dst)
    return {"name": dst.name, "path": dst.name}


# ---------------------------------------------------------------- 主题图标
def get_topic_emoji(topic: str) -> str:
    """读取主题 emoji（存于主题文件夹内 .nl-topic.json，重命名自动保留）。"""
    try:
        f = resolve_in(get_vault_dir(), topic) / ".nl-topic.json"
    except HTTPException:
        return ""
    if not f.exists():
        return ""
    try:
        return str((json.loads(f.read_text(encoding="utf-8")) or {}).get("emoji", ""))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return ""


def set_topic_emoji(topic: str, emoji: str) -> Dict:
    folder = resolve_in(get_vault_dir(), topic)
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail=f"主题不存在：{topic}")
    emoji = (emoji or "").strip()[:8]
    f = folder / ".nl-topic.json"
    if emoji:
        f.write_text(json.dumps({"emoji": emoji}, ensure_ascii=False), encoding="utf-8")
    elif f.exists():
        f.unlink()
    return {"name": folder.name, "emoji": emoji}


# ---------------------------------------------------------------- 目录树
def get_tree(rel: str = "") -> Dict:
    vault = get_vault_dir()
    root = resolve_in(vault, rel) if rel else vault
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"路径不存在：{rel}")
    return _tree_node(vault, root)


def _tree_node(vault: Path, path: Path) -> Dict:
    rel = path.relative_to(vault).as_posix()
    node: Dict = {"name": path.name or "", "path": rel, "type": "dir" if path.is_dir() else "file"}
    if path.is_dir():
        children = []
        for child in sorted(path.iterdir(), key=lambda c: (c.is_file(), c.name.lower())):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                children.append(_tree_node(vault, child))
            elif child.suffix.lower() == ".md":
                fm, _ = parse_frontmatter(_read_text(child))
                children.append(
                    {
                        "name": child.stem,
                        "path": child.relative_to(vault).as_posix(),
                        "type": "term" if fm.get("type") == "term" else "note",
                        "title": fm.get("title") or child.stem,
                        "finished": bool(fm.get("finished")),
                    }
                )
        node["children"] = children
    return node


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


# ---------------------------------------------------------------- 置顶 / 看完标记
def list_pinned() -> List[Dict]:
    """全库扫描 frontmatter 里 pinned: true 的笔记（跨主题，按更新时间倒序）。"""
    vault = get_vault_dir()
    out = []
    for p in _iter_md(vault):
        fm, _ = parse_frontmatter(_read_text(p))
        if not fm.get("pinned"):
            continue
        rel = p.relative_to(vault).as_posix()
        out.append(
            {
                "path": rel,
                "name": p.stem,
                "title": fm.get("title") or p.stem,
                "topic": p.relative_to(vault).parts[0],
                "type": "term" if fm.get("type") == "term" else "note",
                "finished": bool(fm.get("finished")),
                "updated_at": datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )
    out.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return out


def _set_fm_flag(rel: str, key: str, value: bool) -> Dict:
    """写/清 frontmatter 布尔标记（pinned、finished 等），保留其余键与正文。"""
    vault = get_vault_dir()
    path = resolve_in(vault, rel)
    if not path.exists() or path.suffix.lower() != ".md":
        raise HTTPException(status_code=404, detail=f"笔记不存在：{rel}")
    fm, body = parse_frontmatter(_read_text(path))
    if value:
        fm[key] = True
    else:
        fm.pop(key, None)
    path.write_text(build_frontmatter(fm) + body, encoding="utf-8")
    return read_note(path.relative_to(vault).as_posix())


def set_pinned(rel: str, pinned: bool) -> Dict:
    """设置/取消笔记置顶（frontmatter pinned 键）。"""
    return _set_fm_flag(rel, "pinned", pinned)


def set_finished(rel: str, finished: bool) -> Dict:
    """标记/取消笔记「看完」（frontmatter finished 键）。"""
    return _set_fm_flag(rel, "finished", finished)


# ---------------------------------------------------------------- 笔记 CRUD
def read_note(rel: str) -> Dict:
    path = resolve_in(get_vault_dir(), rel)
    if not path.exists() or path.suffix.lower() != ".md":
        raise HTTPException(status_code=404, detail=f"笔记不存在：{rel}")
    content = _read_text(path)
    fm, _ = parse_frontmatter(content)
    stat = path.stat()
    return {
        "path": path.relative_to(get_vault_dir()).as_posix(),
        "name": path.stem,
        "topic": path.relative_to(get_vault_dir()).parts[0],
        "title": fm.get("title") or path.stem,
        "type": "term" if fm.get("type") == "term" else "note",
        "frontmatter": fm,
        "content": content,
        "updated_at": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "size": stat.st_size,
    }


def create_note(rel: str, content: str = "", overwrite: bool = False) -> Dict:
    vault = get_vault_dir()
    path = resolve_in(vault, rel)
    if path.suffix.lower() != ".md":
        path = path.with_suffix(".md")
    if path.exists() and not overwrite:
        raise HTTPException(status_code=409, detail=f"笔记已存在：{path.relative_to(vault).as_posix()}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or f"# {path.stem}\n", encoding="utf-8")
    return read_note(path.relative_to(vault).as_posix())


def save_note(rel: str, content: str) -> Dict:
    vault = get_vault_dir()
    path = resolve_in(vault, rel)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"笔记不存在：{rel}")
    path.write_text(content, encoding="utf-8")
    return read_note(path.relative_to(vault).as_posix())


def delete_note(rel: str) -> None:
    path = resolve_in(get_vault_dir(), rel)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"笔记不存在：{rel}")
    path.unlink()


def move_note(src: str, dst: str) -> Dict:
    vault = get_vault_dir()
    s = resolve_in(vault, src)
    if not s.exists():
        raise HTTPException(status_code=404, detail=f"笔记不存在：{src}")
    d = resolve_in(vault, dst)
    if d.suffix.lower() != ".md":
        d = d.with_suffix(".md")
    if d.exists():
        raise HTTPException(status_code=409, detail=f"目标已存在：{d.relative_to(vault).as_posix()}")
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))
    return read_note(d.relative_to(vault).as_posix())


# ---------------------------------------------------------------- 搜索
def search_vault(query: str, topic: str = "", limit: int = 50) -> List[Dict]:
    vault = get_vault_dir()
    q = query.strip().lower()
    if not q:
        return []
    root = resolve_in(vault, topic) if topic else vault
    results = []
    for p in _iter_md(root):
        text = _read_text(p)
        lower = text.lower()
        rel = p.relative_to(vault).as_posix()
        hit_pos = lower.find(q)
        if hit_pos < 0:
            continue
        start = max(0, hit_pos - 60)
        snippet = text[start: hit_pos + len(q) + 80].replace("\n", " ")
        fm, _ = parse_frontmatter(text)
        results.append(
            {
                "path": rel,
                "name": p.stem,
                "title": fm.get("title") or p.stem,
                "snippet": ("…" if start > 0 else "") + snippet + "…",
            }
        )
        if len(results) >= limit:
            break
    return results


# ---------------------------------------------------------------- 双链与反链
def build_link_index() -> Dict[str, Dict]:
    """扫描全库：{note_id: {path, name, title, type, topic, outgoing: [目标名]}}"""
    vault = get_vault_dir()
    index: Dict[str, Dict] = {}
    for p in _iter_md(vault):
        text = _read_text(p)
        fm, _ = parse_frontmatter(text)
        rel = p.relative_to(vault).as_posix()
        nid = rel[:-3]
        index[nid] = {
            "path": rel,
            "id": nid,
            "name": p.stem,
            "title": fm.get("title") or p.stem,
            "type": "term" if fm.get("type") == "term" else "note",
            "topic": p.relative_to(vault).parts[0],
            "outgoing": extract_wiki_links(text),
        }
    return index


def list_backlinks(rel: str) -> List[Dict]:
    vault = get_vault_dir()
    path = resolve_in(vault, rel)
    target_names = {path.stem, path.name[:-3] if path.name.lower().endswith(".md") else path.stem}
    backlinks = []
    for info in build_link_index().values():
        if info["path"] == path.relative_to(vault).as_posix():
            continue
        if target_names & set(info["outgoing"]):
            text = _read_text(vault / info["path"])
            hit = text.lower().find(path.stem.lower())
            snippet = text[max(0, hit - 40): hit + len(path.stem) + 60].replace("\n", " ") if hit >= 0 else ""
            backlinks.append({**info, "snippet": snippet})
    return backlinks
