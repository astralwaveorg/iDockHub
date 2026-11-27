import json
import re
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_SOURCE_BYTES = 2 * 1024 * 1024


def https_url(value):
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.port not in (None, 443):
        raise ValueError("地址必须使用公开的 HTTPS")
    return url


def validate_source_url(value, owner):
    url = https_url(value)
    host = url.hostname.lower()
    if host == f"{owner.lower()}.github.io":
        return
    parts = unquote(url.path).strip("/").split("/")
    if (host == "raw.githubusercontent.com" and len(parts) >= 4
            and parts[0].lower() == owner.lower() and all(p not in ("", ".", "..") for p in parts)):
        return
    raise ValueError("sourceURL 必须位于仓库所有者的 GitHub Pages 或其 GitHub 原始文件地址")


def download_host(value):
    host = https_url(value).hostname
    if host in ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"):
        return
    if host == "archive.org" or host.endswith(".archive.org"):
        return
    raise ValueError("发布者软件源的 IPA 必须托管在 GitHub 或 Internet Archive")


class CheckedRedirect(HTTPRedirectHandler):
    def __init__(self, check):
        self.check = check

    def redirect_request(self, request, fp, code, message, headers, newurl):
        self.check(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def open_url(url, check, headers=None):
    check(url)
    return build_opener(CheckedRedirect(check)).open(
        Request(url, headers={"User-Agent": "iDockHub", **(headers or {})}), timeout=15
    )


def probe_ipa(url):
    host = https_url(url).hostname
    destinations = []

    def check(value):
        # 只允许从短链接跳入受支持的主机。发布实际 IPA 地址。
        if value == url and host == "tinyurl.com":
            return
        download_host(value)
        if not destinations and unquote(urlsplit(value).path).lower().endswith(".ipa"):
            destinations.append(value)

    with open_url(url, check, {"Range": "bytes=0-3", "Accept-Encoding": "identity"}) as response:
        if response.status == 206:
            match = re.fullmatch(r"bytes 0-3/(\d+)", response.headers.get("Content-Range", ""))
            size = int(match[1]) if match else 0
        else:
            size = int(response.headers.get("Content-Length", "0"))
        if not destinations or not 4 <= size <= 2**31 - 1 or response.read(4) != b"PK\x03\x04":
            raise ValueError("下载地址没有返回可用的 IPA")
        return size, destinations[0]


def published_at(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not timestamp.tzinfo:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def read_app(config, limit):
    repo = config["repo"]
    owner = repo.split("/")[0]
    with open_url(config["sourceURL"], lambda url: validate_source_url(url, owner)) as response:
        payload = response.read(MAX_SOURCE_BYTES + 1)
    if len(payload) > MAX_SOURCE_BYTES:
        raise ValueError("发布者软件源超过 2 MiB")
    source = json.loads(payload)
    if not isinstance(source, dict) or not isinstance(source.get("apps"), list):
        raise ValueError("发布者软件源没有有效的 apps 列表")
    bundle = config.get("bundleIdentifier")
    apps = [
        app for app in source["apps"]
        if isinstance(app, dict) and (not bundle or app.get("bundleIdentifier") == bundle)
    ]
    if len(apps) != 1:
        raise ValueError("发布者软件源中找不到唯一的应用。请核对 bundleIdentifier")

    app = apps[0]
    overrides = config["overrides"]
    fields = ("name", "bundleIdentifier", "developerName", "localizedDescription", "iconURL")
    result = {field: overrides.get(field, app.get(field)) for field in fields}
    if not all(isinstance(value, str) and value.strip() for value in result.values()):
        raise ValueError("发布者软件源缺少应用名称、标识、作者、描述或图标")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", result["bundleIdentifier"]):
        raise ValueError("发布者软件源中的 bundleIdentifier 无效")
    https_url(result["iconURL"])
    tint = overrides.get("tintColor", app.get("tintColor"))
    if isinstance(tint, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}", tint):
        result["tintColor"] = tint

    permissions = app.get("appPermissions")
    if permissions is not None or "entitlements" in overrides:
        if permissions is None:
            permissions = {}
        if not isinstance(permissions, dict):
            raise ValueError("发布者软件源的 appPermissions 格式无效")
        privacy, entitlements = permissions.get("privacy", {}), permissions.get("entitlements", [])
        if not isinstance(privacy, dict) or not isinstance(entitlements, (dict, list)) or not all(
            isinstance(key, str) for key in entitlements
        ):
            raise ValueError("发布者软件源的权限字段格式无效")
        added = overrides.get("entitlements", [])
        if isinstance(entitlements, list):
            entitlements = sorted(set(entitlements) | set(added))
        else:
            entitlements = {**dict.fromkeys(added), **entitlements}
        result["appPermissions"] = {"privacy": privacy, "entitlements": entitlements}

    versions = app.get("versions")
    if not isinstance(versions, list):
        raise ValueError("发布者软件源没有有效的 versions 列表")
    candidates = []
    for version in versions:
        if not isinstance(version, dict) or not all(
            isinstance(version.get(field), str) and version[field].strip()
            for field in ("version", "date", "downloadURL")
        ):
            raise ValueError("发布者软件源的版本信息不完整")
        candidates.append((published_at(version["date"]), version))

    result["versions"] = []
    seen = set()
    for timestamp, version in sorted(candidates, key=lambda pair: pair[0], reverse=True):
        key = (version["version"], version.get("buildVersion"))
        if key in seen:
            continue
        try:
            size, download_url = probe_ipa(version["downloadURL"])
        except HTTPError as exc:
            if exc.code not in (404, 410):
                raise
            print(f"警告：跳过 {repo} {version['version']}：IPA 已不可下载（HTTP {exc.code}）。")
            continue
        entry = {
            "version": version["version"],
            "date": timestamp.date().isoformat(),
            "localizedDescription": (version.get("localizedDescription") or "")[:500],
            "downloadURL": download_url,
            "size": size,
        }
        for field in ("buildVersion", "minOSVersion"):
            if isinstance(version.get(field), str) and version[field]:
                entry[field] = version[field]
        result["versions"].append(entry)
        seen.add(key)
        if len(result["versions"]) == limit:
            break
    if not result["versions"]:
        raise ValueError("发布者软件源没有可下载的 IPA")
    return result
