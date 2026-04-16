# Recomp Discovery Template

A GitHub Actions-powered mod registry for N64 Recomp projects. On a scheduled cron, this workflow automatically fetches mod metadata from **GitHub Releases** and **Thunderstore**, then writes a single `mods.json` file — which your Recomp project can point to directly as a raw JSON endpoint.

---

## How It Works

```
config.json  →  fetch_mods.py  →  mods.json  (committed back to the repo)
```

1. You define your mod sources in `config.json`.
2. A GitHub Actions workflow runs `fetch_mods.py` on a schedule (cron).
3. The script fetches the latest release data from each source, extracts metadata and thumbnails from `.nrm` / `.zip` assets, and writes `mods.json`.
4. The workflow commits `mods.json` back to the repository.
5. Your Recomp project reads the raw `mods.json` URL to display the Discovery.

---

## Setup

### 1. Fork or use this template

Click **"Use this template"** to create your own mod registry repository.

### 2. Create your `config.json`

Copy `example-config.json` to `config.json` and edit it to point at your mod sources:

```json
{
  "github_sources": [
    {
      "enabled": true,
      "repo": "YourOrg/YourModRepo",
      "nrm_file": "your_mod.nrm",
      "zip_containing_nrm": "YourMod.zip"
    }
  ],
  "thunderstore_sources": [
    {
      "enabled": true,
      "community": "your-community-slug",
      "game_id": "your_game_id",
      "filters": {
        "include_nsfw": false,
        "categories": [],
        "namespaces": []
      }
    }
  ],
  "output_file": "mods.json"
}
```

> **Note:** `config.json` is gitignored by default if you want to keep your sources private, or you can commit it publicly — it's just JSON.

### 3. Enable the GitHub Actions workflow

The workflow is already included at `.github/workflows/update_mods.yml`. To activate the scheduled runs, uncomment the `schedule` block in that file:

```yaml
on:
  schedule:
    - cron: "0 * * * *"   # runs every hour — adjust as needed
  workflow_dispatch:
```
---

## Pointing Your Recomp Project at the Registry

Once the workflow has run at least once, `mods.json` will be committed to your repository. Use the **raw** GitHub URL as your Discovery endpoint:

```
https://raw.githubusercontent.com/<owner>/<repo>/mod_data/mods.json
```

For example:
```
https://raw.githubusercontent.com/Killklli/RecompDiscoveryTemplate/mod_data/mods.json
```

Pass this URL to your Recomp project's Discovery configuration and it will always serve the latest data on every cron update — no server required.

---

## config.json Reference

### GitHub Sources

| Field | Required | Description |
|---|---|---|
| `enabled` | No | Set to `false` to skip this source. Defaults to `true`. |
| `repo` | **Yes** | GitHub repository in `owner/repo` format. |
| `nrm_file` | No | Exact filename of the `.nrm` asset to prefer. |
| `zip_containing_nrm` | No | Exact filename of a `.zip` that contains the `.nrm` inside. |

Asset selection priority: `zip_containing_nrm` → `nrm_file` → any `.nrm` → any `.zip`.

### Thunderstore Sources

| Field | Required | Description |
|---|---|---|
| `enabled` | No | Set to `false` to skip this source. Defaults to `true`. |
| `community` | **Yes** | Thunderstore community slug (e.g. `zelda-64-recompiled`). |
| `game_id` | No | Game identifier to tag entries with. |
| `filters.include_nsfw` | No | Include NSFW packages. Defaults to `false`. |
| `filters.categories` | No | Allowlist of category names. Empty = all categories. |
| `filters.namespaces` | No | Allowlist of package namespaces/owners. Empty = all namespaces. |

### Top-level Fields

| Field | Default | Description |
|---|---|---|
| `output_file` | `mods.json` | Filename to write the registry data to. |

---

## mods.json Schema

Each entry in `mods.json` is keyed by the mod's display name:

```json
{
  "Author/ModName": {
    "file_url": "https://...",
    "short_description": "A short description of the mod.",
    "version": "1.0.0",
    "id": "author_modname",
    "game_id": "your_game_id",
    "thumbnail_image": "data:image/png;base64,..."
  }
}
```

Thunderstore entries use `thumbnail_url` (a remote URL) instead of the inline `thumbnail_image` data-URI used by GitHub sources.

---

## Local Development

```powershell
pip install -r requirements.txt
# Copy example config and edit it
Copy-Item example-config.json config.json
python fetch_mods.py
```

A `GITHUB_TOKEN` environment variable is optional but recommended to avoid GitHub API rate limits:

```powershell
$env:GITHUB_TOKEN = "ghp_..."
python fetch_mods.py
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP requests to GitHub and Thunderstore APIs |
| `Pillow` | Converting `.dds` thumbnails from NRM files to PNG |
