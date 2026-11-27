import json
from datetime import date
from fnmatch import fnmatchcase
from urllib.parse import quote
from urllib.request import Request, urlopen

from ipa_metadata import inspect_asset


def github(repo, token, endpoint=""):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "iDockHub",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com/repos/{repo}{endpoint}", headers=headers)
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def fetch_releases(config, token):
    repo, channel = config["repo"], config["channel"]
    if channel == "latest":
        return [github(repo, token, "/releases/latest")]
    tag = config.get("tag", "")
    if channel == "nightly" and not any(c in tag for c in "*?["):
        return [github(repo, token, f"/releases/tags/{quote(tag, safe='')}")]

    releases = []
    page = 1
    while True:
        batch = github(repo, token, f"/releases?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("GitHub 返回的 Release 列表无效")
        releases.extend(batch)
        if len(batch) < 100:
            return releases
        page += 1


def asset_fingerprint(asset):
    # 同名资产可能被替换。使用 GitHub 记录区分不同的上传。
    return json.dumps(
        [asset["id"], asset["updated_at"], asset["size"], asset.get("digest")],
        separators=(",", ":"),
    )


def select_assets(config, releases):
    channel = config["channel"]
    candidates = []
    for release in releases:
        if release["draft"] or not release["published_at"]:
            continue
        if channel in ("stable", "latest") and release["prerelease"]:
            continue
        if channel == "prerelease" and not release["prerelease"]:
            continue
        if channel == "nightly" and not fnmatchcase(release["tag_name"], config["tag"]):
            continue
        candidates.append(release)

    for release in sorted(candidates, key=lambda item: (item["published_at"], item["id"]), reverse=True):
        assets = [
            asset for asset in release["assets"]
            if asset.get("state") == "uploaded" and asset["name"].lower().endswith(".ipa")
            and fnmatchcase(asset["name"].lower(), config["assetPattern"].lower())
        ]
        if len(assets) > 1:
            names = "、".join(sorted(asset["name"] for asset in assets))
            raise ValueError(f"{release['tag_name']} 匹配多个 IPA：{names}。请用 assetPattern 指定一个")
        if assets:
            yield release, assets[0]


def read_app(config, token, old_assets, limit):
    repo = config["repo"]
    details = github(repo, token)
    if details.get("private"):
        raise ValueError("仓库是私有的，订阅者无法下载 IPA")

    from_cache = {}
    versions, metadata, seen = [], [], set()
    for release, asset in select_assets(config, fetch_releases(config, token)):
        fingerprint = asset_fingerprint(asset)
        info = old_assets.get(fingerprint)
        if info is None or "devices" not in info:
            print(f"正在检查 {config['repo']} 的 {asset['name']}。", flush=True)
            info = inspect_asset(asset)
        key = (info["version"], info["buildVersion"])
        if key in seen:
            continue
        if metadata and metadata[0]["bundleIdentifier"] != info["bundleIdentifier"]:
            raise ValueError("多个版本的 bundleIdentifier 不一致。请检查 assetPattern")
        published = (asset["updated_at"] if config["channel"] == "nightly" else release["published_at"])[:10]
        date.fromisoformat(published)
        version = {
            "version": info["version"],
            "buildVersion": info["buildVersion"],
            "date": published,
            "localizedDescription": (release.get("body") or "")[:500],
            "downloadURL": asset["browser_download_url"],
            "size": asset["size"],
        }
        if "minOSVersion" in info:
            version["minOSVersion"] = info["minOSVersion"]
        versions.append(version)
        metadata.append(info)
        from_cache[fingerprint] = info
        seen.add(key)
        if len(versions) == limit:
            break

    if not versions:
        raise ValueError("当前渠道没有匹配的 IPA。请检查 GitHub Release 和 assetPattern")

    owner, repo_name = repo.split("/")
    overrides = config["overrides"]
    entitlements, privacy = set(overrides.get("entitlements", [])), {}
    for info in reversed(metadata):
        if info["needsEntitlementsOverride"] and "entitlements" not in overrides:
            raise ValueError("IPA 权限只提供 DER 格式。请在 overrides.entitlements 中列出实际权限")
        entitlements.update(info["entitlements"])
        privacy.update(info["privacy"])
    latest = metadata[0]
    app = {
        "name": overrides.get("name") or latest["name"] or repo_name,
        "bundleIdentifier": latest["bundleIdentifier"],
        "developerName": overrides.get("developerName", owner),
        "localizedDescription": overrides.get("localizedDescription") or details.get("description") or repo_name,
        "iconURL": overrides.get("iconURL") or details["owner"]["avatar_url"],
        "appPermissions": {"entitlements": sorted(entitlements), "privacy": privacy},
        "versions": versions,
    }
    if "tintColor" in overrides:
        app["tintColor"] = overrides["tintColor"]
    return app, from_cache
