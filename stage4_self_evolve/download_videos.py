import argparse
import ipaddress
import json
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import DEFAULT_OUTPUT_DIR, PROJECT_ROOT, read_jsonl, video_id_from_url, write_jsonl


LOCAL_DEPS = PROJECT_ROOT / ".deps" / "python"
if LOCAL_DEPS.exists():
    sys.path.insert(0, str(LOCAL_DEPS))


def import_ytdlp() -> Any:
    try:
        import yt_dlp  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "yt_dlp is not installed. Install it with: "
            "/mnt/afs/zhangyaolun/.conda/envs/stream/bin/pip install --target .deps/python yt-dlp"
        ) from exc
    return yt_dlp


def install_network_overrides(host_ip_args: Optional[List[str]], force_ipv4: bool) -> None:
    if not host_ip_args and not force_ipv4:
        return
    overrides: Dict[str, str] = {}
    for item in host_ip_args:
        if "=" not in item:
            raise ValueError(f"Invalid --host-ip value {item!r}; expected HOST=IP")
        host, ip = item.split("=", 1)
        host = host.strip().lower()
        ip = ip.strip()
        ipaddress.ip_address(ip)
        if not host:
            raise ValueError(f"Invalid --host-ip value {item!r}; host is empty")
        overrides[host] = ip

    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):  # type: ignore[no-untyped-def]
        ip = overrides.get(str(host).lower())
        if not ip:
            infos = original_getaddrinfo(host, port, family, type, proto, flags)
            if force_ipv4:
                ipv4_infos = [info for info in infos if info[0] == socket.AF_INET]
                return ipv4_infos or infos
            return infos
        ip_obj = ipaddress.ip_address(ip)
        ip_family = socket.AF_INET6 if ip_obj.version == 6 else socket.AF_INET
        if family not in (0, socket.AF_UNSPEC, ip_family):
            return original_getaddrinfo(host, port, family, type, proto, flags)
        sock_type = type or socket.SOCK_STREAM
        sock_proto = proto or socket.IPPROTO_TCP
        return [(ip_family, sock_type, sock_proto, "", (ip, port))]

    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]


def find_existing(cache_dir: Path, video_id: str) -> Optional[Path]:
    for suffix in (".mp4", ".mkv", ".webm", ".mov", ".avi"):
        path = cache_dir / f"{video_id}{suffix}"
        if path.exists() and path.stat().st_size > 0:
            return path
    matches = sorted(cache_dir.glob(f"{video_id}.*"))
    for path in matches:
        if path.suffix.lower() in {".json", ".part", ".ytdl"}:
            continue
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def row_video_id(row: Dict[str, Any]) -> str:
    return str(row.get("video_id") or video_id_from_url(str(row.get("url", ""))))


def download_one(yt_dlp: Any, row: Dict[str, Any], cache_dir: Path, args: argparse.Namespace) -> Dict[str, Any]:
    video_id = row_video_id(row)
    url = row.get("url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else "")
    result = {
        "candidate_id": row.get("candidate_id"),
        "video_id": video_id,
        "url": url,
        "status": "pending",
        "local_video_path": None,
        "error": None,
    }
    if not video_id or not url:
        result["status"] = "skipped_missing_video_id_or_url"
        return result
    existing = find_existing(cache_dir, video_id)
    if existing:
        result["status"] = "exists"
        result["local_video_path"] = str(existing)
        return result

    cache_dir.mkdir(parents=True, exist_ok=True)
    fmt = f"bv*[height<={args.max_height}]+ba/b[height<={args.max_height}]/best" if args.max_height else "bv*+ba/best"
    ydl_opts = {
        "format": fmt,
        "outtmpl": str(cache_dir / "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": not args.verbose,
        "no_warnings": not args.verbose,
        "retries": args.retries,
        "fragment_retries": args.fragment_retries,
        "socket_timeout": args.socket_timeout,
        "ignoreerrors": False,
        "continuedl": True,
        "overwrites": False,
    }
    if args.yt_dlp_cache_dir:
        ydl_opts["cachedir"] = str(args.yt_dlp_cache_dir)
    if args.no_check_certificate:
        ydl_opts["nocheckcertificate"] = True
    if args.js_runtime:
        runtime_config = {}
        if args.js_runtime_path:
            runtime_config["path"] = str(args.js_runtime_path)
        ydl_opts["js_runtimes"] = {args.js_runtime: runtime_config}
    if args.remote_components:
        ydl_opts["remote_components"] = [
            part.strip() for part in args.remote_components.split(",") if part.strip()
        ]
    if args.cookies:
        ydl_opts["cookiefile"] = str(args.cookies)
    if args.proxy:
        ydl_opts["proxy"] = args.proxy
    if args.force_ipv4:
        ydl_opts["source_address"] = "0.0.0.0"
    if args.cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = tuple(part.strip() for part in args.cookies_from_browser.split(":") if part.strip())
    if args.youtube_player_client:
        ydl_opts["extractor_args"] = {
            "youtube": {
                "player_client": [part.strip() for part in args.youtube_player_client.split(",") if part.strip()]
            }
        }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([str(url)])
        downloaded = find_existing(cache_dir, video_id)
        if downloaded:
            result["status"] = "downloaded"
            result["local_video_path"] = str(downloaded)
        else:
            result["status"] = "failed_no_output_file"
            result["error"] = "yt-dlp completed but no output file was found"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
    return result


def attach_paths(rows: List[Dict[str, Any]], manifest_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id = {row.get("video_id"): row.get("local_video_path") for row in manifest_rows if row.get("local_video_path")}
    out = []
    for row in rows:
        merged = dict(row)
        local_path = by_id.get(row_video_id(row))
        if local_path:
            merged["local_video_path"] = local_path
            merged["video_path"] = local_path
        out.append(merged)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT_DIR / "candidates.jsonl")
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_OUTPUT_DIR / "video_download_manifest.jsonl")
    parser.add_argument("--annotated-output", type=Path, default=None)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_OUTPUT_DIR / "video_cache")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-height", type=int, default=720)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--fragment-retries", type=int, default=3)
    parser.add_argument("--socket-timeout", type=float, default=30.0)
    parser.add_argument("--yt-dlp-cache-dir", type=Path, default=PROJECT_ROOT / ".deps" / "yt-dlp-cache")
    parser.add_argument("--no-check-certificate", action="store_true")
    parser.add_argument("--proxy", default=None, help="HTTP/SOCKS proxy URL, for example http://host:port or socks5://host:port")
    parser.add_argument("--force-ipv4", action="store_true", help="Bind yt-dlp requests to IPv4.")
    parser.add_argument(
        "--host-ip",
        action="append",
        default=None,
        help="Override DNS for a host, e.g. www.youtube.com=172.217.25.142. Can be repeated.",
    )
    parser.add_argument("--js-runtime", choices=["quickjs", "node", "deno", "bun"], default=None)
    parser.add_argument("--js-runtime-path", type=Path, default=None)
    parser.add_argument(
        "--remote-components",
        default=None,
        help="Comma-separated yt-dlp remote components to allow, e.g. ejs:github or ejs:github,ejs:npm.",
    )
    parser.add_argument("--cookies", type=Path, default=None)
    parser.add_argument(
        "--cookies-from-browser",
        default=None,
        help="yt-dlp browser cookie spec, for example chrome or firefox:default",
    )
    parser.add_argument(
        "--youtube-player-client",
        default=None,
        help="Comma-separated yt-dlp YouTube player clients, for example web,mweb,tv",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    install_network_overrides(args.host_ip, args.force_ipv4)
    rows = read_jsonl(args.input)
    if args.offset:
        rows = rows[args.offset :]
    if args.limit is not None:
        rows = rows[: args.limit]
    yt_dlp = import_ytdlp()
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    with args.manifest_output.open("w", encoding="utf-8") as manifest_file:
        for row in rows:
            result = download_one(yt_dlp, row, args.cache_dir, args)
            manifest_rows.append(result)
            manifest_file.write(json.dumps(result, ensure_ascii=False) + "\n")
            manifest_file.flush()
    if args.annotated_output:
        write_jsonl(args.annotated_output, attach_paths(rows, manifest_rows))

    counts: Dict[str, int] = {}
    for row in manifest_rows:
        status = str(row.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps({"rows": len(manifest_rows), "status_counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
