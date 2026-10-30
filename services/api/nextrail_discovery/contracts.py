"""Explicit provider authorization and bounded source URL contracts."""

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
METHODS = frozenset({"manual", "official_api", "rss"})
SOURCE_FIELDS = frozenset({
    "id", "provider_id", "provider_name", "provider_website",
    "source_url", "method", "authorization", "allowed_hosts", "synthetic"
})


class SourceContractError(ValueError):
    """Source cannot be used safely or does not match the reviewed contract."""


def valid_id(value):
    return isinstance(value, str) and bool(ID.fullmatch(value))


def hostname(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise SourceContractError("Invalid or excessive URL")
    if any(ord(ch) <= 32 or ord(ch) == 127 for ch in value):
        raise SourceContractError("URL contains control or whitespace")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise SourceContractError("Invalid URL structure") from exc
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not host
        or parsed.fragment
    ):
        raise SourceContractError("Only credential-free HTTPS URLs without fragments are allowed")
    host = host.lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise SourceContractError("IP address URLs are prohibited")
    if not HOST.fullmatch(host):
        raise SourceContractError("Invalid public DNS hostname")
    return host


@dataclass(frozen=True)
class Source:
    id: str
    provider_id: str
    provider_name: str
    provider_website: str
    source_url: str
    method: str
    authorization: str
    allowed_hosts: tuple[str, ...]
    synthetic: bool

    @classmethod
    def from_dict(cls, raw):
        if not isinstance(raw, dict) or set(raw) != SOURCE_FIELDS:
            raise SourceContractError("Unknown or missing source properties")
        if not valid_id(raw["id"]) or not valid_id(raw["provider_id"]):
            raise SourceContractError("Source and provider IDs must use lowercase slugs")
        name = raw["provider_name"]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise SourceContractError("Invalid provider name")
        if raw["method"] not in METHODS:
            raise SourceContractError("Unrecognized source integration method")
        if raw["authorization"] not in ("approved", "pending"):
            raise SourceContractError("Unrecognized authorization status")
        if type(raw["synthetic"]) is not bool:
            raise SourceContractError("Synthetic status must be boolean")
        hosts = raw["allowed_hosts"]
        if not isinstance(hosts, list) or not 1 <= len(hosts) <= 8:
            raise SourceContractError("Specify 1-8 explicitly allowed hosts")
        if any(not isinstance(host, str) or not HOST.fullmatch(host) or host != host.lower()
               for host in hosts) or len(hosts) != len(set(hosts)):
            raise SourceContractError("Invalid allowed hosts")
        website_host = hostname(raw["provider_website"])
        source_host = hostname(raw["source_url"])
        if website_host not in hosts or source_host not in hosts:
            raise SourceContractError("Source and provider URLs require explicit host authorization")
        return cls(
            id=raw["id"],
            provider_id=raw["provider_id"],
            provider_name=name.strip(),
            provider_website=raw["provider_website"],
            source_url=raw["source_url"],
            method=raw["method"],
            authorization=raw["authorization"],
            allowed_hosts=tuple(hosts),
            synthetic=raw["synthetic"],
        )

    def check_url(self, url):
        if hostname(url) not in self.allowed_hosts:
            raise SourceContractError("Record URL host is outside the source allowlist")

    def require_usable(self, preview=False):
        if self.synthetic:
            if not preview:
                raise SourceContractError("Synthetic source cannot enter public discovery")
            return
        if self.authorization != "approved":
            raise SourceContractError("Source must be explicitly approved before ingestion")


def load_registry(value):
    if not isinstance(value, dict) or set(value) != {"schema_version", "sources"}:
        raise SourceContractError("Invalid source registry structure")
    if value["schema_version"] != "1.0.0":
        raise SourceContractError("Unsupported source registry version")
    rows = value["sources"]
    if not isinstance(rows, list) or len(rows) > 100:
        raise SourceContractError("Invalid source registry size")
    sources = [Source.from_dict(row) for row in rows]
    if len({s.id for s in sources}) != len(sources):
        raise SourceContractError("Duplicate source ID")
    providers = {}
    for source in sources:
        current = (source.provider_name, source.provider_website, source.authorization,
                   source.synthetic, source.method)
        if source.provider_id in providers and providers[source.provider_id] != current:
            raise SourceContractError("Conflicting provider definitions")
        providers[source.provider_id] = current
    return sources
