# Reads config.json and writes mods.json for the Recomp Discovery.
# Sources: GitHub Releases and Thunderstore.

from __future__ import annotations

import base64
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import requests


def _fetch_image_as_data_uri(url: str) -> str:
    """Download an image URL and return it as a base64 data-URI string."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/png").split(";")[0].strip()
        encoded = base64.b64encode(resp.content).decode("utf-8")
        return f"data:{content_type};base64,{encoded}"
    except Exception as exc:
        print(f"WARNING | Could not fetch thumbnail {url}: {exc}")
        return ""


def _find_asset(assets: list[dict], nrm_file: str, zip_name: str) -> dict | None:
    # Priority: exact zip name > exact nrm name > any .nrm > any .zip
    if zip_name:
        for a in assets:
            if a["name"] == zip_name:
                return a
    if nrm_file:
        for a in assets:
            if a["name"] == nrm_file:
                return a
    for a in assets:
        if a["name"].endswith(".nrm"):
            return a
    for a in assets:
        if a["name"].endswith(".zip"):
            return a
    return None


def _dds_to_png_data_uri(dds_bytes: bytes) -> str:
    """Convert DDS bytes to a PNG base64 data-URI. Falls back to raw DDS on failure."""
    try:
        from PIL import Image  # type: ignore

        img = Image.open(io.BytesIO(dds_bytes))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{encoded}"
    except Exception as exc:
        print(f"WARNING | DDS conversion failed ({exc}); embedding raw DDS bytes.")
        encoded = base64.b64encode(dds_bytes).decode("utf-8")
        return f"data:image/x-dds;base64,{encoded}"


def _parse_nrm(nrm_bytes: bytes) -> tuple[dict, str]:
    """Extract mod.json and thumb.dds from an NRM (or ZIP containing an NRM)."""
    mod_info: dict = {}
    thumbnail: str = ""

    def _read_nrm_contents(zf: zipfile.ZipFile) -> None:
        nonlocal mod_info, thumbnail
        names_lower = {n.lower(): n for n in zf.namelist()}

        json_key = names_lower.get("mod.json")
        if json_key:
            mod_info = json.loads(zf.read(json_key).decode("utf-8"))
        else:
            print("WARNING | NRM ZIP does not contain mod.json")

        dds_key = names_lower.get("thumb.dds")
        if dds_key:
            thumbnail = _dds_to_png_data_uri(zf.read(dds_key))
        else:
            print("WARNING | NRM ZIP does not contain thumb.dds")

    try:
        with zipfile.ZipFile(io.BytesIO(nrm_bytes)) as outer_zf:
            names_lower = {n.lower(): n for n in outer_zf.namelist()}

            nrm_entry = next(
                (orig for lower, orig in names_lower.items() if lower.endswith(".nrm")),
                None,
            )
            if nrm_entry:
                print(f"INFO | Found NRM inside outer ZIP: {nrm_entry}")
                inner_bytes = outer_zf.read(nrm_entry)
                try:
                    with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner_zf:
                        _read_nrm_contents(inner_zf)
                except zipfile.BadZipFile as exc:
                    print(f"ERROR | Inner NRM is not a valid ZIP: {exc}")
            else:
                _read_nrm_contents(outer_zf)

    except zipfile.BadZipFile as exc:
        print(f"ERROR | Asset is not a valid ZIP/NRM: {exc}")

    return mod_info, thumbnail


def process_github_source(source: dict) -> dict[str, Any] | None:
    """Fetch the latest GitHub release, extract the NRM asset, and return a mod entry."""
    repo = source.get("repo", "")
    if not repo:
        print("WARNING | GitHub source missing 'repo' field, skipping.")
        return None

    nrm_file = source.get("nrm_file", "")
    zip_name = source.get("zip_containing_nrm", "")

    token = os.environ.get("GITHUB_TOKEN")
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    print(f"INFO | GitHub | Fetching latest release for {repo}")

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        print(f"ERROR | GitHub | HTTP error for {repo}: {exc}")
        return None
    except Exception as exc:
        print(f"ERROR | GitHub | Request failed for {repo}: {exc}")
        return None

    release = resp.json()
    assets: list[dict] = release.get("assets", [])

    asset = _find_asset(assets, nrm_file, zip_name)
    if not asset:
        print(f"WARNING | GitHub | No suitable asset found in release for {repo}")
        return None

    file_url: str = asset["browser_download_url"]

    print(f"INFO | GitHub | Downloading NRM asset: {asset['name']}")
    try:
        dl_headers = {**headers, "Accept": "application/octet-stream"}
        dl_resp = requests.get(file_url, headers=dl_headers, timeout=120, stream=True)
        dl_resp.raise_for_status()
        nrm_bytes = b"".join(dl_resp.iter_content(chunk_size=1024 * 64))
    except Exception as exc:
        print(f"ERROR | GitHub | Failed to download asset for {repo}: {exc}")
        return None

    mod_info, thumbnail = _parse_nrm(nrm_bytes)

    release_version: str = release.get("tag_name", "0.0.0").lstrip("v")
    version: str = mod_info.get("version") or release_version
    display_name: str = mod_info.get("display_name") or mod_info.get("id") or repo.split("/")[-1]
    mod_id: str = mod_info.get("id") or display_name.lower().replace(" ", "_")
    game_id: str = mod_info.get("game_id", "")
    short_desc: str = mod_info.get("short_description") or mod_info.get("description", "")

    # Fallback description: first line of the GitHub release body
    if not short_desc:
        body: str = release.get("body") or ""
        short_desc = body.split("\n")[0].strip()

    return {
        display_name: {
            "file_url": file_url,
            "short_description": short_desc,
            "version": version,
            "id": mod_id,
            "game_id": game_id,
            "thumbnail_image": thumbnail,
        }
    }


THUNDERSTORE_API = "https://thunderstore.io"


def _ts_get_packages(community: str) -> list[dict]:
    """Fetch all packages for a Thunderstore community."""
    url = f"{THUNDERSTORE_API}/c/{community}/api/v1/package/"
    print(f"INFO | Thunderstore | Fetching packages for community '{community}'")
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"WARNING | Thunderstore | Primary endpoint failed ({exc}), trying fallback.")

    url = f"{THUNDERSTORE_API}/api/v1/package/?community_slug={community}"
    packages: list[dict] = []
    while url:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        packages.extend(data.get("results", data if isinstance(data, list) else []))
        url = data.get("next") if isinstance(data, dict) else None
    return packages


def _passes_filters(pkg: dict, filters: dict) -> bool:
    include_nsfw: bool = filters.get("include_nsfw", False)
    categories: list[str] = [c.lower() for c in filters.get("categories", [])]
    namespaces: list[str] = [n.lower() for n in filters.get("namespaces", [])]

    if not include_nsfw and pkg.get("has_nsfw_content", False):
        return False

    if namespaces and pkg.get("owner", "").lower() not in namespaces:
        return False

    if categories:
        pkg_cats = [c.lower() for c in pkg.get("categories", [])]
        if not any(c in pkg_cats for c in categories):
            return False

    return True


def process_thunderstore_source(source: dict) -> dict[str, Any]:
    community: str = source.get("community", "")
    game_id: str = source.get("game_id", "")
    filters: dict = source.get("filters", {})

    if not community:
        print("WARNING | Thunderstore source missing 'community', skipping.")
        return {}

    try:
        packages = _ts_get_packages(community)
    except Exception as exc:
        print(f"ERROR | Thunderstore | Failed to fetch packages for '{community}': {exc}")
        return {}

    entries: dict[str, Any] = {}

    for pkg in packages:
        if not _passes_filters(pkg, filters):
            continue

        versions: list[dict] = pkg.get("versions", [])
        if not versions:
            continue

        latest = versions[0]

        mod_name: str = pkg.get("name", "Unknown")
        namespace: str = pkg.get("owner", "")
        display_name: str = f"{namespace}/{mod_name}" if namespace else mod_name
        version: str = latest.get("version_number", "0.0.0")
        raw_download_url: str = latest.get("download_url", "")
        # Thunderstore download URLs are redirects; resolve to the actual ZIP URL.
        file_url: str = raw_download_url
        if raw_download_url:
            try:
                head_resp = requests.head(raw_download_url, allow_redirects=True, timeout=15)
                if head_resp.url != raw_download_url:
                    file_url = head_resp.url
            except Exception as exc:
                print(f"WARNING | Thunderstore | Could not resolve redirect for {display_name}: {exc}")
        description: str = latest.get("description", pkg.get("date_created", ""))
        icon_url: str = latest.get("icon", "")

        # Build a stable mod_id from namespace + name
        mod_id = f"{namespace}_{mod_name}".lower().replace("-", "_").replace(" ", "_")

        entries[display_name] = {
            "file_url": file_url,
            "short_description": description,
            "version": version,
            "id": mod_id,
            "game_id": game_id,
            "thumbnail_url": icon_url,
        }

    print(f"INFO | Thunderstore | Collected {len(entries)} package(s) from community '{community}'")
    return entries


def main() -> None:
    with open("config.json", encoding="utf-8") as fh:
        config = json.load(fh)

    output_file: str = config.get("output_file", "mods.json")
    all_mods: dict[str, Any] = {}

    for source in config.get("github_sources", []):
        if not source.get("enabled", True):
            print(f"INFO | GitHub | Skipping disabled source: {source.get('repo', '?')}")
            continue
        result = process_github_source(source)
        if result:
            all_mods.update(result)

    for source in config.get("thunderstore_sources", []):
        if not source.get("enabled", True):
            print(f"INFO | Thunderstore | Skipping disabled community: {source.get('community', '?')}")
            continue
        entries = process_thunderstore_source(source)
        all_mods.update(entries)

    if not all_mods:
        print("WARNING | No mod entries were collected. Output file will be empty.")

    out_path = Path(__file__).parent / output_file
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(all_mods, fh, indent=2, ensure_ascii=False)

    print(f"INFO | Wrote {len(all_mods)} mod(s) to {out_path}")


if __name__ == "__main__":
    main()
