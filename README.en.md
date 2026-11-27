# iDockHub

[简体中文](README.md) · [![Update the IPA source](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml/badge.svg?branch=main)](https://github.com/astralwaveorg/iDockHub/actions/workflows/update-ipa-source.yml)

iDockHub lists iOS apps for LiveContainer and SideStore. Each download comes from a GitHub Release or the publisher's own source. iDockHub keeps up to three versions per app.

## Add the source

Copy the [source URL](https://raw.githubusercontent.com/astralwaveorg/iDockHub/main/ipa/source.json):

```text
https://raw.githubusercontent.com/astralwaveorg/iDockHub/main/ipa/source.json
```

1. Open **Sources** in LiveContainer. In SideStore, open **Browse** first, then tap **Sources**.
2. Tap **+** and paste the source URL.
3. Confirm that you want to add the source.

<details>
<summary>Links that open the apps</summary>

GitHub README files do not make app protocol links clickable. Use these URLs in an app that supports them:

```text
livecontainer://source?url=https%3A%2F%2Fraw.githubusercontent.com%2Fastralwaveorg%2FiDockHub%2Fmain%2Fipa%2Fsource.json
sidestore://source?url=https%3A%2F%2Fraw.githubusercontent.com%2Fastralwaveorg%2FiDockHub%2Fmain%2Fipa%2Fsource.json
```

</details>

## Apps

<!-- APPS_TABLE_START -->

| App | Latest version | Date (UTC) | Upstream repository |
| --- | --- | --- | --- |
| MoviePilot | 2.0.9 | 2026-11-27 | [jxxghp/MoviePilot-App](https://github.com/jxxghp/MoviePilot-App) |
| uYouEnhanced | 21.20.4 | 2026-10-09 | [arichornlover/uYouEnhanced](https://github.com/arichornlover/uYouEnhanced) |

<!-- APPS_TABLE_END -->

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

List each repository once. Each app ID must be unique. If you remove an entry, the next successful sync removes that app from the source.

### Import from the publisher's source

If a publisher lists IPA files in its own source, use `sourceURL`. Use the publisher's GitHub Pages URL or a raw GitHub file from the same account. If the source lists several apps, set `bundleIdentifier` to select one. Omit `channel` for this type of entry.

uYouEnhanced uses this method. The script keeps the publisher's version and permission records. It checks that the download URL returns an IPA. It supports IPA files on GitHub and the Internet Archive.

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
| `ipa/.sync-state.json` | Generated cache that prevents repeat IPA downloads |
| [`ipa/update_source.py`](ipa/update_source.py) | Sync releases and update the source and app tables |
| [`ipa/ipa_metadata.py`](ipa/ipa_metadata.py) | Read the version and permissions from an IPA |
| [`ipa/publisher_source.py`](ipa/publisher_source.py) | Import a publisher's source and check downloads |
| [`scripts/`](scripts/) | Reserved for iOS, proxy configuration, and automation scripts |
| [`shortcuts/`](shortcuts/) | Reserved for iOS shortcuts |
