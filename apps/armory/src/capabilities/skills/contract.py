from pydantic import BaseModel, Field


class ProposeResult(BaseModel):
    id: int = Field(description="Id of the proposed (or already existing) skill.")
    message: str


class SearchResult(BaseModel):
    count: int = Field(description="Number of active skills returned.")
    message: str


class MarkResult(BaseModel):
    recorded: bool = Field(description="True when the outcome was counted for an active skill.")
    message: str
