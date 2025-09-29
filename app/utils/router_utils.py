from fastapi import APIRouter


def get_router(prefix: str):
    base_prefix = "/caps_lock/api"
    concat_prefix = "/".join([base_prefix, prefix])
    if concat_prefix[-1] == "/":
        concat_prefix = concat_prefix[:-1]
    router = APIRouter(prefix=concat_prefix, tags=[prefix])
    return router
