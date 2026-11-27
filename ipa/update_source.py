import json
import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

IPA_DIR = Path(__file__).resolve().parent
README = IPA_DIR.parent / "README.md"
TABLE_START = "<!-- APPS_TABLE_START -->"
TABLE_END = "<!-- APPS_TABLE_END -->"
APP_FIELDS = ("name", "bundleIdentifier", "developerName", "localizedDescription", "iconURL")
SOURCE = {
    "name": "iDockHub IPA Source",
    "subtitle": "Astral 自维护 iOS 开源应用源",
    "description": "每 3 小时自动追踪 GitHub Releases 更新的个人 IPA 软件源",
    "identifier": "org.astralwave.idockhub",
    "sourceURL": "https://raw.githubusercontent.com/astralwaveorg/iDockHub/main/ipa/source.json",
}


def load_config(path):
    configs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(configs, list):
        raise ValueError("apps.json 必须是 JSON 数组")

    seen = set()
    for i, config in enumerate(configs, 1):
        if not isinstance(config, dict):
            raise ValueError(f"第 {i} 项必须是 JSON 对象")
        for field in ("repo", *APP_FIELDS):
            value = config.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"第 {i} 项的 {field} 必须是非空字符串")
        repo = config["repo"]
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo)
            or repo.split("/")[1] in (".", "..")
        ):
            raise ValueError(f"第 {i} 项的 repo 必须是 GitHub 的 owner/repo")
        bundle_id = config["bundleIdentifier"]
        if bundle_id in seen:
            raise ValueError(f"重复的 bundleIdentifier：{bundle_id}")
        seen.add(bundle_id)

        limit = config.get("maxVersions", 5)
        if type(limit) is not int or limit < 1:
            raise ValueError(f"{repo} 的 maxVersions 必须为正整数")
        if type(config.get("includePrerelease", False)) is not bool:
            raise ValueError(f"{repo} 的 includePrerelease 必须为布尔值")
        try:
            config["assetRegex"] = re.compile(config.get("assetRegex", r"\.ipa$"), re.IGNORECASE)
        except (TypeError, re.error) as exc:
            raise ValueError(f"{repo} 的 assetRegex 无效：{exc}") from exc
    return configs


def fetch_releases(repo, token):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "iDockHub",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    page = 1
    while True:
        url = f"https://api.github.com/repos/{repo}/releases?per_page=100&page={page}"
        with urlopen(Request(url, headers=headers), timeout=15) as response:
            releases = json.load(response)
        if not isinstance(releases, list):
            raise ValueError("GitHub 返回的 Release 数据不是数组")
        yield from releases
        if len(releases) < 100:
            break
        page += 1


def build_app(config, releases):
    # GitHub 返回的发布时间是 UTC；按发布时间排序，避免旧标签晚发布时顺序出错。
    candidates = (
        release for release in releases
        if not release["draft"] and release.get("published_at")
        and (config.get("includePrerelease", False) or not release["prerelease"])
    )
    versions = []
    seen = set()
    for release in sorted(candidates, key=lambda item: (item["published_at"], item["id"]), reverse=True):
        version = re.sub(r"^[vV]", "", release["tag_name"], count=1)
        if not version or version in seen:
            continue
        assets = (
            asset for asset in release["assets"]
            if asset["name"].lower().endswith(".ipa") and config["assetRegex"].search(asset["name"])
        )
        # 一个 Release 只收录一个 IPA；有多个匹配时按文件名稳定选择。
        asset = min(assets, key=lambda item: (item["name"].casefold(), item["name"]), default=None)
        if asset is None:
            continue
        versions.append({
            "version": version,
            "date": release["published_at"][:10],
            "localizedDescription": (release.get("body") or "")[:500],
            "downloadURL": asset["browser_download_url"],
            "size": asset["size"],
        })
        seen.add(version)
        if len(versions) == config.get("maxVersions", 5):
            break
    if not versions:
        raise ValueError("没有符合条件的 IPA Release")

    app = {field: config[field] for field in APP_FIELDS}
    for field in ("tintColor", "appPermissions"):
        if field in config:
            app[field] = config[field]
    app["versions"] = versions
    return app


def markdown_cell(value):
    value = " ".join(value.splitlines())
    return re.sub(r"([\\|`*_[\]<>~&])", r"\\\1", value)


def render_readme(readme, entries):
    if readme.count(TABLE_START) != 1 or readme.count(TABLE_END) != 1:
        raise ValueError("README 应用表格标记缺失或重复")
    start = readme.index(TABLE_START) + len(TABLE_START)
    end = readme.index(TABLE_END)
    if start > end:
        raise ValueError("README 应用表格标记顺序错误")

    newline = "\r\n" if readme[start:].startswith("\r\n") else "\n"
    rows = ["| 应用 | 最新版本 | 更新日期（UTC） | GitHub 仓库 |", "| --- | --- | --- | --- |"]
    for repo, app in entries:
        latest = app["versions"][0]
        rows.append(
            f"| {markdown_cell(app['name'])} | {markdown_cell(latest['version'])} | "
            f"{latest['date']} | [{markdown_cell(repo)}](https://github.com/{repo}) |"
        )
    if not entries:
        rows.append("| 暂无应用 | — | — | — |")
    return readme[:start] + newline * 2 + newline.join(rows) + newline * 2 + readme[end:]


def write_if_changed(path, content):
    data = content.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


def main():
    try:
        configs = load_config(IPA_DIR / "apps.json")
        readme = README.read_bytes().decode("utf-8")
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        entries = []
        for config in configs:
            repo = config["repo"]
            try:
                app = build_app(config, fetch_releases(repo, token))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                print(f"警告：跳过 {repo}：{exc}", file=sys.stderr)
                continue
            entries.append((repo, app))
            print(f"已获取 {app['name']} {app['versions'][0]['version']}，共 {len(app['versions'])} 个版本")

        if configs and not entries:
            print("错误：所有仓库均未获取到可用 IPA，保留现有软件源和 README。", file=sys.stderr)
            return 1

        source = {**SOURCE, "apps": [app for _, app in entries], "news": []}
        new_readme = render_readme(readme, entries)
        new_source = json.dumps(source, ensure_ascii=False, indent=2) + "\n"
        source_changed = write_if_changed(IPA_DIR / "source.json", new_source)
        readme_changed = write_if_changed(README, new_readme)
        print("已更新软件源和应用列表。" if source_changed or readme_changed else "软件源和应用列表无变化。")
        return 0
    except (OSError, ValueError) as exc:
        print(f"错误：无法更新软件源：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
