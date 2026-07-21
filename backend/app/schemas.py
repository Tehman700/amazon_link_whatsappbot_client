from pydantic import BaseModel, ConfigDict, Field


# ---- Marketplaces ----

class MarketplaceBase(BaseModel):
    code: str = Field(min_length=2, max_length=8)
    name: str = Field(min_length=1, max_length=64)
    domain: str = Field(min_length=4, max_length=64)
    default_tag: str = Field(default="", max_length=64)


class MarketplaceCreate(MarketplaceBase):
    pass


class MarketplaceOut(MarketplaceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---- Tracking IDs ----

class TrackingIDSet(BaseModel):
    marketplace_id: int
    tag: str = Field(min_length=1, max_length=64)


class TrackingIDOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    marketplace_id: int
    tag: str
    marketplace: MarketplaceOut


# ---- Users ----

class UserBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    whatsapp_number: str = Field(min_length=5, max_length=32)
    email: str | None = None
    link_preference: str = Field(default="direct", pattern="^(direct|hub)$")
    store_name: str = Field(default="", max_length=120)


class UserCreate(UserBase):
    # Create-only: pre-fill this user's tracking IDs from each marketplace's
    # built-in default. Ignored on update.
    apply_default_tags: bool = False


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tracking_ids: list[TrackingIDOut] = []


# ---- Message processing ----

class ProcessRequest(BaseModel):
    sender: str = Field(description="WhatsApp number of the sender")
    text: str = Field(description="Full message text/caption as received")


class ReplacementOut(BaseModel):
    original: str
    rewritten: str
    marketplace_code: str


class SkippedOut(BaseModel):
    url: str
    reason: str


class ProcessResponse(BaseModel):
    text: str
    links_replaced: int
    replacements: list[ReplacementOut]
    skipped: list[SkippedOut]
