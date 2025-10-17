from typing import Optional
from sqlalchemy import UniqueConstraint
from sqlmodel import Field
from app.models.base import BaseModel


class Watchlist(BaseModel, table=True):
    """
    관심종목 그룹 (user별 여러 개)
    """

    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_watchlist_user_name"),
    )

    watchlist_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="워치리스트 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    user_id: int = Field(
        foreign_key="users.user_id",
        nullable=False,
        description="소유 사용자",
    )

    name: str = Field(
        max_length=100,
        nullable=False,
        description="워치리스트 이름",
    )


class WatchlistItem(BaseModel, table=True):
    """
    관심종목 항목 (watchlist_id, ticker_id 유니크)
    """

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "ticker_id", name="uq_watchlistitem_pair"),
    )

    item_id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="워치리스트 아이템 ID",
        sa_column_kwargs={"autoincrement": True},
    )

    watchlist_id: int = Field(
        foreign_key="watchlists.watchlist_id",
        nullable=False,
        description="워치리스트 ID",
    )

    ticker_id: int = Field(
        foreign_key="tickers.ticker_id",
        nullable=False,
        description="종목 ID",
    )

    
