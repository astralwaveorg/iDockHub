import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

from github_release import read_app as read_github_app
from publisher_source import https_url, public_host, read_app as read_publisher_app, validate_source_url

IPA_DIR = Path(__file__).resolve().parent
README_TABLES = {
    "README.md": (
        ("应用", "最新版本", "设备", "日期（UTC）", "上游"),
        "暂无应用", "未确认", "GitHub Releases", "作者源",
    ),
    "README.en.md": (
        ("App", "Latest version", "Devices", "Date (UTC)", "Upstream"),
        "No apps listed", "Unverified", "GitHub Releases", "Publisher source",
    ),
}
TABLE_START = "<!-- APPS_TABLE_START -->"
TABLE_END = "<!-- APPS_TABLE_END -->"
MAX_VERSIONS = 3
CHANNELS = {"stable", "latest", "nightly", "prerelease"}
APP_FIELDS = {"name", "developerName", "localizedDescription", "iconURL", "tintColor", "entitlements"}
SOURCE = {
    "name": "iDockHub IPA Source",
    "subtitle": "个人自维护 iOS 开源应用源",
    "description": "收录来自 GitHub Releases 和项目维护者软件源的 IPA。每 3 小时检查一次更新。",
    "identifier": "org.astralwave.idockhub",
    "sourceURL": "https://raw.githubusercontent.com/astralwaveorg/iDockHub/main/ipa/source.json",
    "iconURL": "https://cdn.jsdelivr.net/gh/astralwaveorg/iDockHub@main/ipa/icons/idockhub.png",
    "tintColor": "5DA9F3",
}


def markdown_cell(value):
    value = " ".join(value.splitlines())
    return re.sub(r"([\\|`*_[\]<>~&])", r"\\\1", value)


def render_readme(path, entries, headings, empty_label, unknown, release_label, source_label):
    readme = path.read_bytes().decode("utf-8")
    if readme.count(TABLE_START) != 1 or readme.count(TABLE_END) != 1:
        raise ValueError(f"{path.name} 的应用表格标记缺失或重复")
    start = readme.index(TABLE_START) + len(TABLE_START)
    end = readme.index(TABLE_END)
    if start > end:
        raise ValueError(f"{path.name} 的应用表格标记顺序错误")

    newline = "\r\n" if readme[start:].startswith("\r\n") else "\n"
    rows = ["| " + " | ".join(headings) + " |", "| " + " | ".join(["---"] * len(headings)) + " |"]
    for config, app, devices in entries:
        repo = config["repo"]
        latest = app["versions"][0]
        upstream = (
            f"[{source_label}]({config['sourceURL']})" if "sourceURL" in config
            else f"[{release_label}](https://github.com/{repo}/releases)"
        )
        rows.append(
            f"| {markdown_cell(app['name'])} | {markdown_cell(latest['version'])} | "
            f"{' / '.join(devices) or unknown} | {latest['date']} | {upstream} |"
        )
    if not entries:
        rows.append(f"| {empty_label} |  |  |  |  |")
    return readme[:start] + newline * 2 + newline.join(rows) + newline * 2 + readme[end:]


def write_if_changed(path, content):
    data = content.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


def entry_key(config):
    repo = config["repo"].lower()
    bundle = config.get("bundleIdentifier")
    return f"{repo}:{bundle}" if bundle else repo


def load_config(path):
    configs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(configs, list):
        raise ValueError("apps.json 必须是 JSON 数组")

    seen = set()
    for i, config in enumerate(configs, 1):
        if not isinstance(config, dict):
            raise ValueError(f"apps.json 第 {i} 项必须是 JSON 对象")
        allowed = {
            "repo", "channel", "tag", "assetPattern", "overrides",
            "sourceURL", "bundleIdentifier", "downloadHosts", "devices",
        }
        if unknown := config.keys() - allowed:
            raise ValueError(f"apps.json 第 {i} 项有未知字段：{', '.join(sorted(unknown))}")
        repo = config.get("repo")
        if (
            not isinstance(repo, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo)
            or repo.split("/")[1] in (".", "..")
        ):
            raise ValueError(f"apps.json 第 {i} 项的 repo 必须是 GitHub 的 owner/repo")
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

        if "sourceURL" in config:
            if config.keys() & {"channel", "tag", "assetPattern"}:
                raise ValueError(f"{repo} 的 sourceURL 不能与 Release 渠道字段一起填写")
            if not isinstance(config["sourceURL"], str):
                raise ValueError(f"{repo} 的 sourceURL 必须是字符串")
            source_host = https_url(config["sourceURL"]).hostname
            validate_source_url(config["sourceURL"], repo.split("/")[0], source_host)
            if any(char in config["sourceURL"] for char in "<>|()"):
                raise ValueError(f"{repo} 的 sourceURL 包含无效字符，请使用百分号编码")
            if "bundleIdentifier" in config and (
                not isinstance(config["bundleIdentifier"], str)
                or not re.fullmatch(r"[A-Za-z0-9.-]+", config["bundleIdentifier"])
            ):
                raise ValueError(f"{repo} 的 bundleIdentifier 无效")
            if "downloadHosts" in config:
                hosts = config["downloadHosts"]
                if not isinstance(hosts, list) or not hosts or not all(public_host(host) for host in hosts):
                    raise ValueError(f"{repo} 的 downloadHosts 必须是小写公开域名数组，不支持通配符")
                config["downloadHosts"] = sorted(set(hosts))
            if "devices" in config:
                devices = config["devices"]
                if not isinstance(devices, list) or not devices or not all(d in ("iPhone", "iPad") for d in devices):
                    raise ValueError(f"{repo} 的 devices 只能列出 iPhone 和 iPad")
                config["devices"] = [device for device in ("iPhone", "iPad") if device in devices]
            config.setdefault("overrides", {})
        else:
            if config.keys() & {"bundleIdentifier", "downloadHosts", "devices"}:
                raise ValueError(f"{repo} 只有使用 sourceURL 时才能填写 bundleIdentifier、downloadHosts 或 devices")

            config.setdefault("channel", "stable")
            config.setdefault("assetPattern", "*.ipa")
            config.setdefault("overrides", {})
            if channel == "nightly":
                config.setdefault("tag", "nightly")
        key = entry_key(config)
        if key in seen:
            raise ValueError(f"应用配置重复：{key}。同一发布者软件源的应用用 bundleIdentifier 区分")
        seen.add(key)
    return configs


def config_fingerprint(config):
    # devices 只影响文档，不影响是否可以沿用上次的软件源。
    selection = {key: value for key, value in config.items() if key != "devices"}
    data = json.dumps(selection, sort_keys=True, separators=(",", ":")).encode()
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
            key = entry_key(config)
            old = previous_state.get(key, {})
            if not old and key != repo.lower():
                legacy = previous_state.get(repo.lower(), {})
                if legacy.get("bundleIdentifier") == config.get("bundleIdentifier"):
                    old = legacy
            try:
                if "sourceURL" in config:
                    app, cached = read_publisher_app(config, MAX_VERSIONS), {}
                    devices = config.get("devices", [])
                else:
                    app, cached = read_github_app(config, token, old.get("assets", {}), MAX_VERSIONS)
                    devices = next(iter(cached.values()))["devices"]
                if old.get("config") == signature and old["bundleIdentifier"] != app["bundleIdentifier"]:
                    raise ValueError("上游 IPA 的应用标识已改变。请核对渠道和资产")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                app = previous_apps.get(old.get("bundleIdentifier"))
                if not (transient(exc) and old.get("config") == signature and app):
                    print(f"警告：跳过 {repo}：{exc}", file=sys.stderr)
                    continue
                print(f"警告：暂时无法更新 {repo}，保留上次结果：{exc}", file=sys.stderr)
                cached = old["assets"]
                devices = config.get("devices", []) if "sourceURL" in config else old.get("devices", [])
            else:
                updated += 1
                print(f"已获取 {app['name']} {app['versions'][0]['version']}，共 {len(app['versions'])} 个版本。")

            bundle = app["bundleIdentifier"]
            if bundle in bundles:
                raise ValueError(f"应用标识重复：{bundle}。请保留一个对应的仓库")
            bundles.add(bundle)
            entries.append((config, app, devices))
            state[key] = {"config": signature, "bundleIdentifier": bundle, "assets": cached, "devices": devices}

        if configs and not updated:
            print("错误：没有仓库完成同步。已保留现有软件源和文档。", file=sys.stderr)
            return 1

        source = {**SOURCE, "apps": [app for _, app, _ in entries], "news": []}
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
