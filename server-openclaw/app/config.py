import ipaddress
import os
from dataclasses import dataclass
from typing import Optional


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    openclaw_gateway_url: str
    openclaw_gateway_token: str
    stackchan_bridge_token: str
    public_domain: str
    lan_host: str
    port: int
    whisper_model: str
    whisper_model_dir: str
    piper_model_path: str
    data_dir: str
    allow_lan_bypass: bool
    trust_proxy_headers: bool


def load_settings() -> Settings:
    return Settings(
        openclaw_gateway_url=os.getenv("OPENCLAW_GATEWAY_URL", "ws://host.docker.internal:18789").strip(),
        openclaw_gateway_token=os.getenv("OPENCLAW_GATEWAY_TOKEN", "").strip(),
        stackchan_bridge_token=os.getenv("STACKCHAN_BRIDGE_TOKEN", "").strip(),
        public_domain=os.getenv("PUBLIC_DOMAIN", "stackchan.example.com").strip(),
        lan_host=os.getenv("LAN_HOST", "192.168.1.100").strip(),
        port=int(os.getenv("PORT", "8765")),
        whisper_model=os.getenv("WHISPER_MODEL", "base.en").strip(),
        whisper_model_dir=os.getenv("WHISPER_MODEL_DIR", "/opt/models/whisper").strip(),
        piper_model_path=os.getenv("PIPER_MODEL_PATH", "/opt/models/piper/en_US-lessac-medium.onnx").strip(),
        data_dir=os.getenv("DATA_DIR", "/app/data").strip(),
        allow_lan_bypass=_env_bool("ALLOW_LAN_BYPASS", True),
        trust_proxy_headers=_env_bool("TRUST_PROXY_HEADERS", False),
    )


def _extract_ip(
    client_host: Optional[str],
    x_forwarded_for: Optional[str],
    trust_proxy_headers: bool = False,
) -> Optional[str]:
    if trust_proxy_headers and x_forwarded_for:
        first = x_forwarded_for.split(",")[0].strip()
        if first:
            return first
    return client_host


def is_lan_or_local(
    client_host: Optional[str],
    x_forwarded_for: Optional[str] = None,
    trust_proxy_headers: bool = False,
) -> bool:
    ip_str = _extract_ip(client_host, x_forwarded_for, trust_proxy_headers=trust_proxy_headers)
    if not ip_str:
        return False
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        return ip_obj.is_private or ip_obj.is_loopback
    except ValueError:
        return ip_str in {"localhost", "host.docker.internal"}


def is_authorized(
    settings: Settings,
    auth_header: Optional[str],
    query_token: Optional[str],
    client_host: Optional[str],
    x_forwarded_for: Optional[str] = None,
) -> bool:
    expected = settings.stackchan_bridge_token

    provided = None
    if auth_header:
        val = auth_header.strip()
        if val.lower().startswith("bearer "):
            provided = val[7:].strip()
        else:
            provided = val
    elif query_token:
        provided = query_token.strip()

    if expected and provided == expected:
        return True

    if settings.allow_lan_bypass and is_lan_or_local(
        client_host,
        x_forwarded_for,
        trust_proxy_headers=settings.trust_proxy_headers,
    ):
        if provided is None or provided == "":
            return True

    return False
