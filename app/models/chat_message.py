from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str
    # "text" or "voice". Marks how the user asked, so the frontend can keep a
    # voice transcript internal on reload instead of showing it as plain text.
    mode: str = "text"