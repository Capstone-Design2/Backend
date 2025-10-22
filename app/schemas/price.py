from pydantic import BaseModel


class YfinanceRequest(BaseModel):
    ticker_name: str
    period: str = "1y"
    interval: str = "1D"
