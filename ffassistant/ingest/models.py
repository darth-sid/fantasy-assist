from pydantic import BaseModel


class NewsItem(BaseModel):
    doc_id: str
    url: str
    source: str
    title: str
    summary: str
    published_at: str
    fetched_at: str
    raw: dict[str, str | None]
