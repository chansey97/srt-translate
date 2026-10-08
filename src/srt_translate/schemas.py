from pydantic import BaseModel, ConfigDict, Field


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Entry(SchemaModel):
    n: int
    text: str


class Entity(SchemaModel):
    source: str = Field(min_length=1)
    context: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    type: str = Field(min_length=1)
    subtype: str = Field(min_length=1)
    translation: str = Field(min_length=1)
    entity_confidence: float = Field(ge=0, le=1)
    type_confidence: float = Field(ge=0, le=1)
    translation_confidence: float = Field(ge=0, le=1)


class EntitiesResponse(SchemaModel):
    entities: list[Entity]


class TranslationResponse(SchemaModel):
    entries: list[Entry]

