"""python -m geniai: runs the service on HOST and PORT.

One process, one worker: the per-conversation lanes (KeyedQueue) and the burst timers live in memory.
uvicorn's access log is off because it would print the webhook token, which is part of the URL; the
app logs each request itself with the token masked (see main.create_app).
"""

import uvicorn

from geniai.config import load_config
from geniai.main import create_app


def main() -> None:
    config = load_config()
    uvicorn.run(create_app(config), host=config.host, port=config.port, access_log=False)


if __name__ == "__main__":
    main()
