from arq.connections import RedisSettings
from app.config import get_settings

def get_redis_settings() -> RedisSettings:

    settings = get_settings()
    url = settings.redis_url
    
    url_no_scheme = url.replace("redis://", "")

    parts = url_no_scheme.split("/")
    host_port = parts[0]
    database = int(parts[1]) if len(parts) > 1 else 0
    
    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host = host_port
        port = 6379
    
    return RedisSettings(
        host=host,
        port=port,
        database=database,
    )
