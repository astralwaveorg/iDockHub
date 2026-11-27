import json
import re
from datetime import datetime, timezone
from email.message import Message
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_SOURCE_BYTES = 2 * 1024 * 1024
GITHUB_ASSET_HOSTS = {"release-assets.githubusercontent.com", "objects.githubusercontent.com"}
HOST_PATTERN = r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]*"


def https_url(value):
    if not isinstance(value, str) or re.search(r"[\\\s]", value):
        raise ValueError("地址必须使用公开的 HTTPS")
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.port not in (None, 443):
        raise ValueError("地址必须使用公开的 HTTPS")
    return url


def public_host(host):
    return (
        isinstance(host, str) and re.fullmatch(HOST_PATTERN, host) is not None
        and not host.endswith((".local", ".localhost", ".internal", ".test", ".invalid"))
        and host != "tinyurl.com"
    )


def validate_source_url(value, owner, configured_host=None):
    url = https_url(value)
    host = url.hostname.lower()
    if host == f"{owner.lower()}.github.io":
        return
    parts = unquote(url.path).strip("/").split("/")
    if (host == "raw.githubusercontent.com" and len(parts) >= 4
            and parts[0].lower() == owner.lower() and all(p not in ("", ".", "..") for p in parts)):
        return
    if (host == configured_host and public_host(host)
            and not host.endswith(".github.io") and host != "raw.githubusercontent.com"):
        return
    raise ValueError("sourceURL 必须使用仓库所有者的 GitHub 地址或配置中明确指定的公开域名")


def download_host(value, extra_hosts=()):
    host = https_url(value).hostname
    if host == "github.com" or host in GITHUB_ASSET_HOSTS or host in extra_hosts:
        return
    if host == "archive.org" or host.endswith(".archive.org"):
        return
    raise ValueError(f"IPA 的下载或跳转域名未获准：{host}。请核对 downloadHosts")


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


def probe_ipa(url, extra_hosts=(), source_check=None):
    host = https_url(url).hostname
    destinations = []

    def check(value):
        location = https_url(value)
        if host == "tinyurl.com" and location.hostname == "tinyurl.com" and value == url:
            return
        if source_check and location.hostname == "raw.githubusercontent.com":
            source_check(value)
        else:
            download_host(value, extra_hosts)
        # GitHub 资产 CDN 的签名链接会过期，不能写进软件源。
        if (not destinations and location.hostname not in GITHUB_ASSET_HOSTS
                and unquote(location.path).lower().endswith(".ipa")):
            destinations.append(value)

    with open_url(url, check, {"Range": "bytes=0-3", "Accept-Encoding": "identity"}) as response:
        if response.status == 206:
            match = re.fullmatch(r"bytes 0-3/(\d+)", response.headers.get("Content-Range", ""))
            size = int(match[1]) if match else 0
        else:
            size = int(response.headers.get("Content-Length", "0"))
        disposition = Message()
        if header := response.headers.get("Content-Disposition"):
            disposition["Content-Disposition"] = header
        filename = disposition.get_filename("") or ""
        if (not destinations and host not in GITHUB_ASSET_HOSTS | {"tinyurl.com"}
                and filename.lower().endswith(".ipa")):
            destinations.append(url)
        if not destinations or not 4 <= size <= 2**31 - 1 or response.read(4) != b"PK\x03\x04":
            raise ValueError("下载地址没有返回可用的 IPA")
        return size, destinations[0]


def published_at(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not timestamp.tzinfo:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def version_entries(app):
    versions = app.get("versions")
    if isinstance(versions, list) and versions:
        return versions
    if "downloadURL" in app:
        return [{
            **app,
            "date": app.get("versionDate"),
            "localizedDescription": app.get("versionDescription"),
        }]
    raise ValueError("发布者软件源没有有效的 versions 或旧版下载字段")


def read_app(config, limit):
    repo = config["repo"]
    owner = repo.split("/")[0]
    source_url = config["sourceURL"]
    source_host = https_url(source_url).hostname

    def check_source(url):
        validate_source_url(url, owner, source_host)

    with open_url(source_url, check_source) as response:
        payload = response.read(MAX_SOURCE_BYTES + 1)
        base_url = response.geturl()
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
    name = overrides.get("name") or app.get("name") or repo.split("/")[1]
    result = {
        "name": name,
        "bundleIdentifier": app.get("bundleIdentifier"),
        "developerName": overrides.get("developerName") or app.get("developerName") or owner,
        "localizedDescription": overrides.get("localizedDescription") or app.get("localizedDescription") or name,
        "iconURL": overrides.get("iconURL") or app.get("iconURL") or f"https://github.com/{quote(owner)}.png",
    }
    if not all(isinstance(value, str) and value.strip() for value in result.values()):
        raise ValueError("发布者软件源缺少应用名称、标识、作者、描述或图标")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", result["bundleIdentifier"]):
        raise ValueError("发布者软件源中的 bundleIdentifier 无效")
    result["iconURL"] = urljoin(base_url, result["iconURL"])
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
        if (
            not isinstance(privacy, dict) or not all(isinstance(value, str) for value in privacy.values())
            or not isinstance(entitlements, (dict, list)) or not all(isinstance(key, str) for key in entitlements)
        ):
            raise ValueError("发布者软件源的权限字段格式无效")
        result["appPermissions"] = {
            "privacy": privacy,
            "entitlements": sorted(set(entitlements) | set(overrides.get("entitlements", []))),
        }

    candidates = []
    for version in version_entries(app):
        try:
            if not isinstance(version, dict) or not all(
                isinstance(version.get(field), str) and version[field].strip()
                for field in ("version", "date", "downloadURL")
            ):
                raise ValueError("版本信息不完整")
            candidates.append((published_at(version["date"]), version))
        except (ValueError, OverflowError) as exc:
            print(f"警告：跳过 {repo} 的一条版本记录：{exc}。")

    result["versions"] = []
    seen = set()
    hosts = {source_host, https_url(base_url).hostname, *config.get("downloadHosts", [])}
    for timestamp, version in sorted(candidates, key=lambda pair: pair[0], reverse=True):
        build = version.get("buildVersion")
        key = (version["version"], build if isinstance(build, str) and build else None)
        if key in seen:
            continue
        try:
            url = urljoin(base_url, version["downloadURL"])
            size, download_url = probe_ipa(url, hosts, check_source)
        except HTTPError as exc:
            if exc.code not in (404, 410):
                raise
            print(f"警告：跳过 {repo} {version['version']}：IPA 已不可下载（HTTP {exc.code}）。")
            continue
        except ValueError as exc:
            print(f"警告：跳过 {repo} {version['version']}：{exc}。")
            continue
        description = version.get("localizedDescription")
        entry = {
            "version": version["version"],
            "date": timestamp.date().isoformat(),
            "localizedDescription": description[:500] if isinstance(description, str) else "",
            "downloadURL": download_url,
            "size": size,
        }
        for field in ("buildVersion", "minOSVersion", "maxOSVersion"):
            if isinstance(version.get(field), str) and version[field]:
                entry[field] = version[field]
        result["versions"].append(entry)
        seen.add(key)
        if len(result["versions"]) == limit:
            break
    if not result["versions"]:
        raise ValueError("发布者软件源没有可下载的 IPA")
    return result
