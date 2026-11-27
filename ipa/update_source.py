import hashlib
import json
import os
import re
import sys
from datetime import date
from fnmatch import fnmatchcase
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from ipa_metadata import inspect_asset

IPA_DIR = Path(__file__).resolve().parent
README_TABLES = {
    "README.md": (("应用", "最新版本", "日期（UTC）", "上游仓库"), "暂无应用"),
    "README.en.md": (("App", "Latest version", "Date (UTC)", "Upstream repository"), "No apps listed"),
}
TABLE_START = "<!-- APPS_TABLE_START -->"
TABLE_END = "<!-- APPS_TABLE_END -->"
MAX_VERSIONS = 3
CHANNELS = {"stable", "latest", "nightly", "prerelease"}
APP_FIELDS = {"name", "developerName", "localizedDescription", "iconURL", "tintColor", "entitlements"}
SOURCE = {
    "name": "iDockHub IPA Source",
    "subtitle": "个人自维护 iOS 开源应用源",
    "description": "从 GitHub Releases 收录开源 iOS 应用。每 3 小时检查一次更新。",
    "identifier": "org.astralwave.idockhub",
    "sourceURL": "https://raw.githubusercontent.com/astralwaveorg/iDockHub/main/ipa/source.json",
}


def markdown_cell(value):
    value = " ".join(value.splitlines())
    return re.sub(r"([\\|`*_[\]<>~&])", r"\\\1", value)


def render_readme(path, entries, headings, empty_label):
    readme = path.read_bytes().decode("utf-8")
    if readme.count(TABLE_START) != 1 or readme.count(TABLE_END) != 1:
        raise ValueError(f"{path.name} 的应用表格标记缺失或重复")
    start = readme.index(TABLE_START) + len(TABLE_START)
    end = readme.index(TABLE_END)
    if start > end:
        raise ValueError(f"{path.name} 的应用表格标记顺序错误")

    newline = "\r\n" if readme[start:].startswith("\r\n") else "\n"
    rows = ["| " + " | ".join(headings) + " |", "| --- | --- | --- | --- |"]
    for repo, app in entries:
        latest = app["versions"][0]
        rows.append(
            f"| {markdown_cell(app['name'])} | {markdown_cell(latest['version'])} | "
            f"{latest['date']} | [{markdown_cell(repo)}](https://github.com/{repo}) |"
        )
    if not entries:
        rows.append(f"| {empty_label} |  |  |  |")
    return readme[:start] + newline * 2 + newline.join(rows) + newline * 2 + readme[end:]


def write_if_changed(path, content):
    data = content.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


def load_config(path):
    configs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(configs, list):
        raise ValueError("apps.json 必须是 JSON 数组")

    seen = set()
    for i, config in enumerate(configs, 1):
        if not isinstance(config, dict):
            raise ValueError(f"apps.json 第 {i} 项必须是 JSON 对象")
        allowed = {"repo", "channel", "tag", "assetPattern", "overrides"}
        if unknown := config.keys() - allowed:
            raise ValueError(f"apps.json 第 {i} 项有未知字段：{', '.join(sorted(unknown))}")
        repo = config.get("repo")
        if (
            not isinstance(repo, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo)
            or repo.split("/")[1] in (".", "..")
        ):
            raise ValueError(f"apps.json 第 {i} 项的 repo 必须是 GitHub 的 owner/repo")
        if repo.lower() in seen:
            raise ValueError(f"仓库重复：{repo}。每个仓库只配置一次")
        seen.add(repo.lower())
        channel = config.get("channel", "stable")
        if not isinstance(channel, str) or channel not in CHANNELS:
            raise ValueError(f"{repo} 的 channel 可填：{', '.join(sorted(CHANNELS))}")
        if "tag" in config and channel != "nightly":
            raise ValueError(f"{repo} 只有 nightly 渠道可以填写 tag")
        for key in ("tag", "assetPattern"):
            if key in config and (not isinstance(config[key], str) or not config[key].strip()):
                raise ValueError(f"{repo} 的 {key} 必须是非空字符串")
        if "tag" in config and config["tag"] in (".", ".."):
            raise ValueError(f"{repo} 的 tag 无效")
        overrides = config.get("overrides", {})
        if not isinstance(overrides, dict) or overrides.keys() - APP_FIELDS:
            raise ValueError(f"{repo} 的 overrides 包含未知字段或格式无效")
        for key, value in overrides.items():
            if key == "entitlements":
                if not isinstance(value, list) or not all(isinstance(e, str) and e.strip() for e in value):
                    raise ValueError(f"{repo} 的 entitlements 必须是字符串数组")
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f"{repo} 的 {key} 必须是非空字符串")
        if "iconURL" in overrides:
            url = urlsplit(overrides["iconURL"])
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError(f"{repo} 的 iconURL 必须是公开的 HTTPS 地址")
        if "tintColor" in overrides and not re.fullmatch(r"#?[0-9a-fA-F]{6}", overrides["tintColor"]):
            raise ValueError(f"{repo} 的 tintColor 必须是六位十六进制颜色")

        config.setdefault("channel", "stable")
        config.setdefault("assetPattern", "*.ipa")
        config.setdefault("overrides", {})
        if channel == "nightly":
            config.setdefault("tag", "nightly")
    return configs


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


def build_app(config, token, old_assets):
    repo = config["repo"]
    details = github(repo, token)
    if details.get("private"):
        raise ValueError("仓库是私有的，订阅者无法下载 IPA")

    from_cache = {}
    versions, metadata, seen = [], [], set()
    for release, asset in select_assets(config, fetch_releases(config, token)):
        fingerprint = asset_fingerprint(asset)
        info = old_assets.get(fingerprint)
        if info is None:
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
        if len(versions) == MAX_VERSIONS:
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


def config_fingerprint(config):
    data = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def read_generated(path, default):
    if not path.exists():
        return default
    data = json.loads(path.read_bytes())
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} 必须包含 JSON 对象")
    return data


def transient(exc):
    if isinstance(exc, HTTPError):
        headers = exc.headers or {}
        return exc.code in (408, 429) or 500 <= exc.code < 600 or (
            exc.code == 403 and (
                headers.get("X-RateLimit-Remaining") == "0" or headers.get("Retry-After") is not None
            )
        )
    return isinstance(exc, OSError)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def main():
    source_path, state_path = IPA_DIR / "source.json", IPA_DIR / ".sync-state.json"
    try:
        configs = load_config(IPA_DIR / "apps.json")
        previous_state = read_generated(state_path, {})
        previous_apps = {
            app["bundleIdentifier"]: app for app in read_generated(source_path, {}).get("apps", [])
        }
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        entries, state, bundles = [], {}, set()
        updated = 0
        for config in configs:
            repo = config["repo"]
            signature = config_fingerprint(config)
            old = previous_state.get(repo.lower(), {})
            try:
                app, cached = build_app(config, token, old.get("assets", {}))
                if old.get("config") == signature and old["bundleIdentifier"] != app["bundleIdentifier"]:
                    raise ValueError("上游 IPA 的应用标识已改变。请核对渠道和资产")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                app = previous_apps.get(old.get("bundleIdentifier"))
                if not (transient(exc) and old.get("config") == signature and app):
                    print(f"警告：跳过 {repo}：{exc}", file=sys.stderr)
                    continue
                print(f"警告：暂时无法更新 {repo}，保留上次结果：{exc}", file=sys.stderr)
                cached = old["assets"]
            else:
                updated += 1
                print(f"已获取 {app['name']} {app['versions'][0]['version']}，共 {len(app['versions'])} 个版本。")

            bundle = app["bundleIdentifier"]
            if bundle in bundles:
                raise ValueError(f"应用标识重复：{bundle}。请保留一个对应的仓库")
            bundles.add(bundle)
            entries.append((repo, app))
            state[repo.lower()] = {"config": signature, "bundleIdentifier": bundle, "assets": cached}

        if configs and not updated:
            print("错误：没有仓库完成同步。已保留现有软件源和文档。", file=sys.stderr)
            return 1

        source = {**SOURCE, "apps": [app for _, app in entries], "news": []}
        outputs = {source_path: json_text(source), state_path: json_text(state)}
        for filename, labels in README_TABLES.items():
            path = IPA_DIR.parent / filename
            outputs[path] = render_readme(path, entries, *labels)
        changed = [path.name for path, content in outputs.items() if write_if_changed(path, content)]
        print("已更新：" + "、".join(changed) if changed else "软件源和文档无变化。")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"错误：无法更新软件源：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
