# iDockHub

[![更新 IPA 软件源](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml/badge.svg?branch=main)](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml)

个人 iOS 资产中心。IPA 软件源每 3 小时检查一次上游 GitHub Releases，下载链接直指上游发布的 IPA。这里也预留了 iOS 脚本和快捷指令目录。

## 订阅 IPA 软件源

**[打开订阅地址](https://raw.githubusercontent.com/astralwaveorg/iDockHub/main/ipa/source.json)**

```text
https://raw.githubusercontent.com/astralwaveorg/iDockHub/main/ipa/source.json
```

在 LiveContainer 中打开 **Sources**，或在 SideStore 中打开 **Browse → Sources**。点 **+**，粘贴上方地址并确认添加。

<details>
<summary>客户端直达链接</summary>

支持应用链接的环境可以用以下地址打开添加页面。GitHub README 会屏蔽这两种协议，在 GitHub 上请按上面的步骤订阅。

```text
livecontainer://source?url=https%3A%2F%2Fraw.githubusercontent.com%2Fastralwaveorg%2FiDockHub%2Fmain%2Fipa%2Fsource.json
sidestore://source?url=https%3A%2F%2Fraw.githubusercontent.com%2Fastralwaveorg%2FiDockHub%2Fmain%2Fipa%2Fsource.json
```

</details>

## 已收录应用

<!-- APPS_TABLE_START -->

| 应用 | 最新版本 | 更新日期（UTC） | GitHub 仓库 |
| --- | --- | --- | --- |
| MoviePilot | 2.0.9 | 2026-11-27 | [jxxghp/MoviePilot-App](https://github.com/jxxghp/MoviePilot-App) |

<!-- APPS_TABLE_END -->

## 项目结构

```text
ipa/
├── apps.json          # 维护要追踪的仓库与应用信息
├── update_source.py   # 同步 GitHub Releases，生成软件源和上方表格
└── source.json        # 供客户端订阅的生成文件
scripts/               # 预留：iOS、代理分流与自动化脚本
shortcuts/             # 预留：iOS 快捷指令与使用说明
```

## 维护与扩展

在 [`ipa/apps.json`](ipa/apps.json) 的 JSON 数组中新增一项。应用仓库应公开可访问，并把 `.ipa` 文件上传为 GitHub Release 资产。

| 字段 | 填写方法 |
| --- | --- |
| `repo` | GitHub 的 `owner/repo`，例如 `jxxghp/MoviePilot-App`。 |
| `name`、`developerName`、`localizedDescription` | 应用名称、开发者名称、简介。 |
| `bundleIdentifier` | IPA 内 `Info.plist` 的 `CFBundleIdentifier`，每个应用必须唯一。 |
| `iconURL`、`tintColor` | 公开可访问的图标 URL；可选主题色，例如 `#5E5CE6`。 |
| `appPermissions` | 应用有权限时，按 IPA 内实际使用的权限填写 `privacy` 和 `entitlements`，供客户端在安装前核对。 |
| `assetRegex` | 匹配 IPA 文件名的正则表达式，不区分大小写。JSON 中默认为 `"\\.ipa$"`。若一个 Release 有多个 IPA，可用 `"-ios-unsigned\\.ipa$"` 指定所需版本；仍有多个匹配时按文件名选第一个。 |
| `includePrerelease` | 默认 `false`；设为 `true` 可收录预发行版。草稿始终跳过。 |
| `maxVersions` | 每个应用最多保留的版本数，默认 `5`，按发布时间从新到旧排列。 |

将 `ipa/apps.json` 的变更推送到 `main` 后，GitHub Actions 会自动运行。也可以在 [Actions](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml) 中点击 **Run workflow** 手动触发。生成结果有变化时，工作流才会提交。

本地在仓库根目录运行：

```bash
python3 ipa/update_source.py
```

脚本仅使用 Python 3 标准库。如已在环境中设置 `GITHUB_TOKEN`，脚本会用它向 GitHub API 鉴权；未设置时也可读取公开仓库。单个仓库拉取失败或没有符合条件的 IPA 时，本次生成会跳过该仓库；如果配置非空且全部失败，脚本会保留现有文件并以非零状态退出。请修改 `apps.json`，由脚本重新生成软件源和应用表格。
