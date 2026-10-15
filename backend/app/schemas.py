"""API 请求/响应模型。"""
from typing import List, Optional

from pydantic import BaseModel, Field


# ---- 主题 ----
class TopicCreate(BaseModel):
    name: str


class TopicRename(BaseModel):
    name: str


class TopicEmoji(BaseModel):
    emoji: str = ""


class TopicDelete(BaseModel):
    recursive: bool = False


# ---- 笔记 ----
class NoteCreate(BaseModel):
    path: str
    content: str = ""
    overwrite: bool = False


class NoteSave(BaseModel):
    path: str
    content: str


class NoteMove(BaseModel):
    src: str
    dst: str


class NoteAppend(BaseModel):
    path: str
    text: str
    heading: str = Field("", description="可选的小节标题，如「AI 补充」")


class ReadProgressIn(BaseModel):
    path: str
    ratio: float = Field(0, description="滚动位置占可滚动高度的比例 0~1")
    heading: str = Field("", description="当时可见的最近小节标题 id（可选）")


# ---- 高亮标注 ----
class AnnotationCreate(BaseModel):
    path: str
    quote: str
    prefix: str = ""
    suffix: str = ""
    occurrence: int = 1
    color: Optional[str] = None
    style: Optional[str] = None  # background | font
    comment: str = ""


class AnnotationUpdate(BaseModel):
    color: Optional[str] = None
    style: Optional[str] = None
    comment: Optional[str] = None
    occurrence: Optional[int] = None


# ---- LLM ----
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    stream: bool = False


class GenerateNoteRequest(BaseModel):
    topic: str
    prompt: str = Field(..., description="要生成什么内容的描述/大纲")
    title: Optional[str] = None
    language: str = "zh"
    stream: bool = True
    save_path: Optional[str] = Field(None, description="生成后保存到的库内路径（如 主题/笔记.md）")
    provider: Optional[str] = None
    model: Optional[str] = None
    use_web: bool = Field(False, description="是否联网搜索补充最新资料")


class AskRequest(BaseModel):
    path: str = Field(..., description="当前笔记路径，用于提供全文上下文")
    selected_text: str
    question: str = ""
    context_before: str = ""
    context_after: str = ""
    language: str = "zh"
    stream: bool = True
    save_to_note: bool = Field(False, description="把这次问答追加保存到笔记末尾")
    provider: Optional[str] = None
    model: Optional[str] = None


class TutorChatRequest(BaseModel):
    paths: List[str] = Field(..., description="AI 助教可用的资料（笔记/概念文档）")
    messages: List[ChatMessage]
    language: str = "zh"
    stream: bool = True
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    use_web: bool = Field(False, description="是否联网搜索补充最新资料")


class TermRequest(BaseModel):
    path: str
    term: str
    context_before: str = ""
    context_after: str = ""
    language: str = "zh"
    regenerate: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None


# ---- 考试 ----
class ExamGenerateRequest(BaseModel):
    paths: List[str]
    types: List[str] = ["mcq", "short"]
    count: int = 10
    difficulty: str = "medium"
    language: str = "zh"
    title: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class AttemptRequest(BaseModel):
    answers: List[dict] = Field(..., description="[{question_id, answer}]")
    provider: Optional[str] = None
    model: Optional[str] = None


class TopicArchitectureRequest(BaseModel):
    topic: str
    goal: str = ""
    save_path: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    use_web: bool = Field(False, description="是否联网搜索补充最新资料")


class TopicScaffoldRequest(BaseModel):
    topic: str
    save_path: str = ""
    provider: Optional[str] = None
    model: Optional[str] = None


class StudyGuideRequest(BaseModel):
    paths: List[str]
    language: str = "zh"
    save_path: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    use_web: bool = Field(False, description="是否联网搜索补充最新资料")


# ---- 读书笔记 ----
class BookNotesRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None


# ---- AI 对话 ----
class ChatSessionCreate(BaseModel):
    title: str = ""


class ChatSessionRename(BaseModel):
    title: str


class ChatTurnRequest(BaseModel):
    content: str = ""
    context_paths: List[str] = Field(
        default_factory=list,
        description="@引用/拖入/划选加入的上下文：笔记路径、路径#章节标题，或 text:{\"t\": 选中文字, \"s\": 来源}",
    )
    regenerate: bool = Field(False, description="重新生成：不追加提问，重答最后一问")
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None


# ---- 设置 ----
class ProviderIn(BaseModel):
    id: str
    type: str  # openai | anthropic | gemini
    name: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    models: List[str] = Field(default_factory=list, description="可用模型列表（供前端下拉选择）")


class ProvidersIn(BaseModel):
    providers: List[ProviderIn]


class ActiveProviderIn(BaseModel):
    provider_id: str = ""


class McpCallIn(BaseModel):
    server: str
    tool: str
    arguments: dict = Field(default_factory=dict)


class HighlightIn(BaseModel):
    color: Optional[str] = None
    style: Optional[str] = None


class ExamSettingsIn(BaseModel):
    default_count: Optional[int] = None
    types: Optional[List[str]] = None
    difficulty: Optional[str] = None
