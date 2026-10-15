"""Typed messages and outcomes for the storefront handoff workflow."""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class SellerAsset(BaseModel):
    kind: Literal["seller_asset"]
    order_id: str
    asset_id: str
    download_url: str


class BuyerUpdate(BaseModel):
    kind: Literal["buyer_update"]
    order_id: str
    status: Literal["paid", "cancelled"]


class OrderHandoff(BaseModel):
    kind: Literal["order_handoff"]
    order_id: str
    buyer_id: str
    asset_ids: list[str]


MarketplaceJob = Annotated[
    Union[SellerAsset, BuyerUpdate, OrderHandoff], Field(discriminator="kind")
]


class QueueMessage(BaseModel):
    message_id: str
    payload: MarketplaceJob


class WorkResult(BaseModel):
    message_id: str
    order_id: str
    action: Literal["asset_recorded", "buyer_notified", "order_handed_off"]
