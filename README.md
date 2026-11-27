# iDockHub

[English](README.en.md) · [![更新 IPA 软件源](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml/badge.svg?branch=main)](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml)

iDockHub 为 LiveContainer 和 SideStore 提供 iOS 应用的软件源。下载链接来自上游 GitHub Release 或项目维护者的软件源。每个应用最多保留 3 个版本。

## 订阅软件源

复制[软件源地址](https://raw.githubusercontent.com/astralwaveorg/iDockHub/main/ipa/source.json)：

```text
https://raw.githubusercontent.com/astralwaveorg/iDockHub/main/ipa/source.json
```

1. 在 LiveContainer 中打开 **Sources**。如果用 SideStore，先打开 **Browse**，再点 **Sources**。
2. 点 **+**，粘贴软件源地址。
3. 确认添加。

<details>
<summary>客户端直达链接</summary>

GitHub README 不提供可点击的应用协议链接。在支持这些协议的环境中，可以用以下地址打开添加页面：

```text
livecontainer://source?url=https%3A%2F%2Fraw.githubusercontent.com%2Fastralwaveorg%2FiDockHub%2Fmain%2Fipa%2Fsource.json
sidestore://source?url=https%3A%2F%2Fraw.githubusercontent.com%2Fastralwaveorg%2FiDockHub%2Fmain%2Fipa%2Fsource.json
```

</details>

## 已收录应用

<!-- APPS_TABLE_START -->

| 应用 | 最新版本 | 日期（UTC） | 上游仓库 |
| --- | --- | --- | --- |
| MoviePilot | 2.0.9 | 2026-11-27 | [jxxghp/MoviePilot-App](https://github.com/jxxghp/MoviePilot-App) |
| uYouEnhanced | 21.20.4 | 2026-10-09 | [arichornlover/uYouEnhanced](https://github.com/arichornlover/uYouEnhanced) |

<!-- APPS_TABLE_END -->

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

每个仓库只配置一次。同一个应用标识也只能出现一次。从清单中删掉一条，下一次成功同步时就会移除该应用。

### 从维护者的软件源添加

如果维护者通过自己的软件源发布 IPA，而 GitHub Release 没有附件，可以用 `sourceURL` 导入。填写维护者的 GitHub Pages 地址或同一账号下的 GitHub 原始文件地址。软件源有多个应用时，加 `bundleIdentifier` 指定一个。此方式不需要 `channel`。

uYouEnhanced 使用这种方式。脚本保留发布者提供的版本和权限信息，并检查下载地址能否返回 IPA。当前支持托管在 GitHub 或 Internet Archive 的 IPA。

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
| `ipa/.sync-state.json` | 生成的缓存，避免重复下载同一个 IPA |
| [`ipa/update_source.py`](ipa/update_source.py) | 同步 Release 并更新软件源和文档 |
| [`ipa/ipa_metadata.py`](ipa/ipa_metadata.py) | 读取 IPA 中的版本和权限信息 |
| [`ipa/publisher_source.py`](ipa/publisher_source.py) | 导入维护者的软件源并检查下载地址 |
| [`scripts/`](scripts/) | 预留给 iOS、代理配置和自动化脚本 |
| [`shortcuts/`](shortcuts/) | 预留给 iOS 快捷指令 |
