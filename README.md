# iDockHub

<img src="ipa/icons/idockhub.png" alt="iDockHub 标志" width="96" height="96">

[English](README.en.md) · [![更新 IPA 软件源](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml/badge.svg?branch=main)](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml)

iDockHub 把 GitHub Releases 和应用发布者的软件源汇到同一个订阅地址，供 LiveContainer 和 SideStore 使用。每个应用最多保留 3 个版本，IPA 仍由上游提供。

## 订阅软件源

复制 [jsDelivr 加速地址](https://cdn.jsdelivr.net/gh/astralwaveorg/iDockHub@main/ipa/source.json)：

```text
https://cdn.jsdelivr.net/gh/astralwaveorg/iDockHub@main/ipa/source.json
```

1. 在 LiveContainer 中打开 **Sources**。如果用 SideStore，先打开 **Browse**，再点 **Sources**。
2. 点 **+**，粘贴软件源地址。
3. 确认添加。

如果 CDN 暂不可用，或需要绕过 CDN 缓存查看更新，请用 [GitHub Raw 备用地址](https://raw.githubusercontent.com/astralwaveorg/iDockHub/main/ipa/source.json)。

<details>
<summary>客户端直达链接</summary>

GitHub README 不提供可点击的应用协议链接。在支持这些协议的环境中，可以用以下地址打开添加页面：

```text
livecontainer://source?url=https%3A%2F%2Fcdn.jsdelivr.net%2Fgh%2Fastralwaveorg%2FiDockHub%40main%2Fipa%2Fsource.json
sidestore://source?url=https%3A%2F%2Fcdn.jsdelivr.net%2Fgh%2Fastralwaveorg%2FiDockHub%40main%2Fipa%2Fsource.json
```

</details>

## 已收录应用

<!-- APPS_TABLE_START -->

| 应用 | 最新版本 | 设备 | 日期（UTC） | 上游 |
| --- | --- | --- | --- | --- |
| MoviePilot | 2.0.10 | iPhone / iPad | 2026-11-27 | [GitHub Releases](https://github.com/jxxghp/MoviePilot-App/releases) |
| uYouEnhanced | 21.20.4 | iPhone / iPad | 2026-10-09 | [作者源](https://raw.githubusercontent.com/arichornlover/arichornlover.github.io/main/apps.json) |
| iTorrent | 2.2.0 | iPhone / iPad | 2026-07-19 | [GitHub Releases](https://github.com/XITRIX/iTorrent/releases) |
| PiliNara | 2.2.0 | iPhone / iPad | 2026-11-09 | [GitHub Releases](https://github.com/Starfallan/PiliNara/releases) |
| Nuvio | 1.0.1 | iPhone / iPad | 2026-11-21 | [GitHub Releases](https://github.com/NuvioMedia/NuvioMobile/releases) |
| TGExtra | 11.12.1 | iPhone / iPad | 2025-06-19 | [GitHub Releases](https://github.com/waruhachi/TGExtra/releases) |

<!-- APPS_TABLE_END -->

同一个订阅包含 iPhone 和 iPad 应用。表里的设备对应最新版本：直接发布的 IPA 以包内声明为准；导入的应用没有核对过设备时，会标为「未确认」。Apple TV 使用 tvOS，需要单独的包和安装方式，当前订阅不收录。

## 添加应用

打开 [`ipa/apps.json`](ipa/apps.json)，在数组中加入一条。通常只需要公开仓库的名称，且仓库须在 GitHub Release 中提供可直接下载的 `.ipa` 文件。

```json
{ "repo": "jxxghp/MoviePilot-App" }
```

这条配置追踪 MoviePilot 的稳定版。清单里已有 MoviePilot，新增时请把示例中的仓库名换成你的 `owner/repo`。脚本从 IPA 读取应用标识、名称、版本、构建号和权限。未指定图标时，使用 GitHub 仓库所有者的头像。

| 发布方式 | 配置 | 收录规则 |
| --- | --- | --- |
| 稳定版 | 省略 `channel`，或填 `"stable"` | 跳过预发行版和没有匹配 IPA 的 Release。按发布时间保留最近 3 个。 |
| GitHub 最新发布 | `"channel": "latest"` | 只查看 GitHub 的 `/releases/latest`。该 Release 没有匹配的 IPA 时，报告错误。 |
| 滚动夜版 | `"channel": "nightly"` | 默认追踪 `nightly` 标签。用 `"tag": "dev"` 可改用其他固定标签。固定标签只保留当前 IPA。 |
| 每次新建夜版标签 | `"channel": "nightly", "tag": "nightly-*"` | 匹配标签后按发布时间收录最近 3 个。 |
| 预发行版 | `"channel": "prerelease"` | 只收录 GitHub 标为预发行的 Release，最多 3 个。 |

夜版也必须发布为 GitHub Release 资产。脚本不收录 Actions 临时产物。滚动夜版沿用应用包内的版本号和构建号，上游未修改它们时，客户端可能不会提示更新。夜版表格显示当前 IPA 的更新时间。

通常只要填仓库和渠道。遇到以下情况时，再加字段：

- 同一 Release 有多个 IPA：加 `"assetPattern": "*-ios-unsigned.ipa"` 选定一个。文件名匹配不区分大小写。
- 需要自定义展示信息：在 `overrides` 中填 `name`、`developerName`、`localizedDescription`、`iconURL` 或 `tintColor`。
- 脚本报告无法读取签名中的权限：核对实际权限，并在 `overrides.entitlements` 中列出权限键。

### 从发布者的软件源导入

通过 `sourceURL` 导入某个应用。下面是 uYouEnhanced 的实际配置：

```json
{
  "repo": "arichornlover/uYouEnhanced",
  "sourceURL": "https://raw.githubusercontent.com/arichornlover/arichornlover.github.io/main/apps.json",
  "bundleIdentifier": "com.google.ios.youtube",
  "devices": ["iPhone", "iPad"],
  "overrides": {
    "iconURL": "https://cdn.jsdelivr.net/gh/astralwaveorg/iDockHub@main/ipa/icons/uyouenhanced.png"
  }
}
```

- 源里只有一个应用时，可省略 `bundleIdentifier`。如果想从同一个源导入多个应用，每个应用各写一条，分别指定它的标识。输出源里的应用标识必须唯一。
- 支持 AltStore 风格的 `versions` 数组，以及把 `version`、`versionDate` 和 `downloadURL` 直接放在应用对象里的旧版格式。相对地址以软件源地址为准。此方式不填 `channel`、`tag` 或 `assetPattern`。
- 软件源和下载都用 HTTPS。GitHub Releases、Internet Archive 和软件源所在站点可以直接用。其他 CDN 需明确列出域名，例如 `"downloadHosts": ["cdn.example.org"]`。重定向也按相同规则检查。
- 确认设备支持后，可以写 `"devices": ["iPhone", "iPad"]`。这个字段只影响应用表，不控制客户端的安装兼容性。

脚本会检查下载地址的文件头和大小，跳过已经失效的版本。如果旧源没有权限信息，要求校验权限的客户端仍可能拒绝安装。要停止收录某个应用，从清单中删除对应条目即可。

## 运行同步

GitHub Actions 每 3 小时安排一次同步。推送清单或同步脚本的变更到 `main` 也会触发同步。需要立即运行时，在 [Actions](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml) 中点 **Run workflow**。

在仓库根目录运行以下命令。需要 Python 3.9 或更高版本，无需安装依赖。可以通过环境变量 `GITHUB_TOKEN` 向 GitHub API 鉴权。

```bash
python3 ipa/update_source.py
```

脚本生成软件源、两份应用表和 IPA 检查缓存。工作流只在生成文件有变化时提交。如果上游暂时无法访问，且该应用的配置没变，脚本会保留上次的结果。如果没有仓库完成同步，脚本会报错并保留现有文件。遇到匹配错误时，查看日志中的仓库名和原因，再改清单。

## 目录

| 路径 | 用途 |
| --- | --- |
| [`ipa/apps.json`](ipa/apps.json) | 手动维护的应用清单 |
| [`ipa/source.json`](ipa/source.json) | 生成的软件源 |
| [`ipa/icons/`](ipa/icons/) | iDockHub 标志的 SVG 原稿和 PNG，以及上游应用的图标 |
| `ipa/.sync-state.json` | 生成的缓存，避免重复下载同一个 IPA |
| [`ipa/update_source.py`](ipa/update_source.py) | 读取清单，汇总两个来源，更新软件源和应用表 |
| [`ipa/github_release.py`](ipa/github_release.py) | 选择 GitHub Release 渠道和 IPA |
| [`ipa/ipa_metadata.py`](ipa/ipa_metadata.py) | 读取 IPA 的版本、设备和权限 |
| [`ipa/publisher_source.py`](ipa/publisher_source.py) | 导入发布者的软件源，检查下载地址 |
| [`scripts/`](scripts/) | 预留给 iOS、代理配置和自动化脚本 |
| [`shortcuts/`](shortcuts/) | 预留给 iOS 快捷指令 |
