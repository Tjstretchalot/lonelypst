# 3.5mb to leave a buffer; aiohttp has a 4mb limit, uvicorn is a 16mb limit by default
WEBSOCKET_MAX_COMPAT_SIZE = 3 * 1024 * 1024 + 512 * 1024
