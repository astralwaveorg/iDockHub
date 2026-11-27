# iDockHub

<img src="ipa/icons/idockhub.png" alt="iDockHub logo" width="96" height="96">

[简体中文](README.md) · [![Update the IPA source](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml/badge.svg?branch=main)](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml)

iDockHub combines GitHub Releases and publisher sources in one subscription for LiveContainer and SideStore. It keeps up to three versions per app. The IPA files stay with their original hosts.

## Add the source

Copy the [jsDelivr URL](https://cdn.jsdelivr.net/gh/astralwaveorg/iDockHub@main/ipa/source.json) to load the source through the CDN:

```text
https://cdn.jsdelivr.net/gh/astralwaveorg/iDockHub@main/ipa/source.json
```

1. Open **Sources** in LiveContainer. In SideStore, open **Browse** first, then tap **Sources**.
2. Tap **+** and paste the source URL.
3. Confirm that you want to add the source.

Use the [GitHub Raw URL](https://raw.githubusercontent.com/astralwaveorg/iDockHub/main/ipa/source.json) if the CDN is unavailable or still shows an older copy.

<details>
<summary>Links that open the apps</summary>

GitHub README files do not make app protocol links clickable. Use these URLs in an app that supports them:

```text
livecontainer://source?url=https%3A%2F%2Fcdn.jsdelivr.net%2Fgh%2Fastralwaveorg%2FiDockHub%40main%2Fipa%2Fsource.json
sidestore://source?url=https%3A%2F%2Fcdn.jsdelivr.net%2Fgh%2Fastralwaveorg%2FiDockHub%40main%2Fipa%2Fsource.json
```

</details>

## Apps

<!-- APPS_TABLE_START -->

| App | Latest version | Devices | Date (UTC) | Upstream |
| --- | --- | --- | --- | --- |
| MoviePilot | 2.0.9 | iPhone / iPad | 2026-11-27 | [GitHub Releases](https://github.com/jxxghp/MoviePilot-App/releases) |
| uYouEnhanced | 21.20.4 | iPhone / iPad | 2026-10-09 | [Publisher source](https://raw.githubusercontent.com/arichornlover/arichornlover.github.io/main/apps.json) |
| iTorrent | 2.2.0 | iPhone / iPad | 2026-07-19 | [GitHub Releases](https://github.com/XITRIX/iTorrent/releases) |
| PiliNara | 2.2.0 | iPhone / iPad | 2026-11-09 | [GitHub Releases](https://github.com/Starfallan/PiliNara/releases) |
| Nuvio | 1.0.1 | iPhone / iPad | 2026-11-21 | [GitHub Releases](https://github.com/NuvioMedia/NuvioMobile/releases) |
| TGExtra | 11.12.1 | iPhone / iPad | 2025-06-19 | [GitHub Releases](https://github.com/waruhachi/TGExtra/releases) |

<!-- APPS_TABLE_END -->

The same subscription lists iPhone and iPad apps. The device column applies to the latest version. For GitHub releases, the script reads device support from the IPA. Imported apps show as unverified until someone checks their device support. Apple TV uses tvOS and requires a separate package and installation method. This source does not list tvOS apps.

## Add an app

Open [`ipa/apps.json`](ipa/apps.json) and add an entry to the array. Use a public repository with a downloadable `.ipa` file attached to a GitHub Release.

```json
{ "repo": "jxxghp/MoviePilot-App" }
```

This entry tracks stable MoviePilot releases. The list already contains MoviePilot. Replace its repository name in the example with the `owner/repo` you want to add. The script reads the app ID, name, version, build number, and permissions from the IPA. If you omit the icon, it uses the GitHub repository owner's avatar.

| Release type | Setting | What the source keeps |
| --- | --- | --- |
| Stable | Omit `channel`, or use `"stable"` | The three most recent stable releases with a matching IPA, by release date. |
| GitHub latest | `"channel": "latest"` | Only the Release from GitHub's `/releases/latest` endpoint. If it has no matching IPA, the script reports an error. |
| Rolling nightly | `"channel": "nightly"` | The current IPA on the `nightly` tag. To use a different fixed tag, set `"tag": "dev"`. |
| Nightly with a new tag for each build | `"channel": "nightly", "tag": "nightly-*"` | The three most recent matching releases, by release date. |
| Prerelease | `"channel": "prerelease"` | Up to three releases that GitHub marks as prereleases. |

Nightly builds must also be GitHub Release assets. The script does not list temporary Actions artifacts. A rolling nightly uses the version and build number from the IPA. If both stay the same, a client may not show an update. The app table gives the date of the last update to the nightly IPA.

The repository and channel usually suffice. Add these fields when you need them:

- If a Release has multiple IPAs, add `"assetPattern": "*-ios-unsigned.ipa"` to select one. Filename matching ignores case.
- To change how the app appears, set `name`, `developerName`, `localizedDescription`, `iconURL`, or `tintColor` under `overrides`.
- If the script cannot read the permissions in the signature, check the actual permissions. List their keys in `overrides.entitlements`.

### Import from the publisher's source

Use `sourceURL` to import an app. This is the entry for uYouEnhanced:

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

- If the source lists one app, you can omit `bundleIdentifier`. To import several apps from one source, add an entry for each app and specify its app ID. Each app ID in the output must be unique.
- The script accepts AltStore-style `versions` arrays and older entries with `version`, `versionDate`, and `downloadURL` on the app itself. It resolves relative URLs against the source URL. Omit `channel`, `tag`, and `assetPattern` for these entries.
- The source and downloads must use HTTPS. GitHub Releases, the Internet Archive, and the publisher's source host work by default. For other download hosts, list each domain in `downloadHosts`, for example `"downloadHosts": ["cdn.example.org"]`. The same rules apply to redirects.
- After you check device support, you can set `"devices": ["iPhone", "iPad"]`. This field changes the app table. It does not change which devices can install the app.

The script checks the file header and size and skips expired downloads. If an old source omits permissions, a client that checks them may refuse to install the app. To remove an app from the source, delete its entry from the app list.

## Run the sync

GitHub Actions schedules a sync every three hours. A push to `main` that changes the app list or sync code also starts a run. To start a run yourself, select **Run workflow** in [Actions](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml).

Run this command from the repository root. Use Python 3.9 or later. You do not need to install any dependencies. Set `GITHUB_TOKEN` in your environment if you want to authenticate to the GitHub API.

```bash
python3 ipa/update_source.py
```

The script generates the source, both app tables, and a cache of IPA metadata. The workflow commits only when a generated file changes. If a request fails temporarily and the app configuration stays the same, the script keeps its last result. If no repository syncs, the script reports an error and keeps the existing files. If an IPA does not match, check the repository and error in the log. Then edit the app list.

## Files

| Path | Purpose |
| --- | --- |
| [`ipa/apps.json`](ipa/apps.json) | App list that you edit |
| [`ipa/source.json`](ipa/source.json) | Generated source |
| [`ipa/icons/`](ipa/icons/) | The iDockHub logo in SVG and PNG, plus app icons from publishers |
| `ipa/.sync-state.json` | Generated cache that prevents repeat IPA downloads |
| [`ipa/update_source.py`](ipa/update_source.py) | Read the app list, combine both inputs, and update the source and tables |
| [`ipa/github_release.py`](ipa/github_release.py) | Select GitHub releases and their IPA files |
| [`ipa/ipa_metadata.py`](ipa/ipa_metadata.py) | Read the version, devices, and permissions from an IPA |
| [`ipa/publisher_source.py`](ipa/publisher_source.py) | Import a publisher's source and check downloads |
| [`scripts/`](scripts/) | Reserved for iOS, proxy configuration, and automation scripts |
| [`shortcuts/`](shortcuts/) | Reserved for iOS shortcuts |
