#!/usr/bin/env python3

import asyncio
import json
import os
import sys
import argparse
import random
import time
from pathlib import Path

import aiohttp

def load_env(path):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


load_env(Path(__file__).with_name(".env"))


def required_setting(name):
    value = os.environ.get(name)
    if value is None:
        raise RuntimeError(
            f"Missing required setting: {name}. Set it in .env or the environment."
        )
    return value


RAW = required_setting("RAW")
TARGET = required_setting("TARGET")
try:
    SOURCES = json.loads(required_setting("SOURCES"))
except json.JSONDecodeError as exc:
    raise ValueError("SOURCES in .env must be a JSON array of [path, scheme] pairs") from exc

if not isinstance(SOURCES, list) or any(
        not isinstance(source, list) or len(source) != 2
        or not all(isinstance(value, str) and value for value in source)
        for source in SOURCES):
    raise ValueError("SOURCES in .env must be a JSON array of [path, scheme] pairs")
SOURCES = [tuple(source) for source in SOURCES]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_lists():
    proxies = set()
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as s:
        async def get(path, scheme):
            url = f"{RAW}/{path}"
            try:
                async with s.get(url, timeout=30) as r:
                    text = await r.text()
                    n = 0
                    for line in text.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        hostport = line.split("://")[-1].strip()
                        if ":" in hostport:
                            proxies.add((scheme, hostport))
                            n += 1
                    print(f"[list] {path}: {n} proxies ({scheme})")
            except Exception as e:
                print(f"[list] {path}: LOI {e}")
        await asyncio.gather(*(get(p, sc) for p, sc in SOURCES))
    return proxies


async def check(proxy_url, sem, timeout):
    async with sem:
        try:
            t = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=t,
                                             headers=HEADERS) as s:
                async with s.get(TARGET, proxy=proxy_url,
                                 allow_redirects=True,
                                 ssl=False) as r:
                    await r.read()
                    return r.status
        except Exception:
            return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=200)
    ap.add_argument("--timeout", type=float, default=10)
    ap.add_argument("--out", default="good_proxies.txt")
    args = ap.parse_args()

    proxies = await fetch_lists()
    print(f"[list] tong cong (sau dedup): {len(proxies)}")

    sem = asyncio.Semaphore(args.workers)
    good, bad403, dead = [], 0, 0
    done = 0
    t0 = time.time()

    async def run(scheme, hostport):
        nonlocal bad403, dead, done
        url = f"{scheme}://{hostport}"
        status = await check(url, sem, args.timeout)
        if status == 403:
            bad403 += 1
        elif status is None:
            dead += 1
        elif status < 400:  # 200/301/302... = vao duoc
            good.append((status, url))
        else:
            dead += 1  # 4xx/5xx khac — bo qua
        done += 1
        if done % 200 == 0:
            dt = time.time() - t0
            print(f"[{done}/{len(proxies)}] good={len(good)} 403={bad403} "
                  f"dead={dead} ({dt:.0f}s)")

    await asyncio.gather(*(run(sc, hp) for sc, hp in proxies))

    random.shuffle(good)
    Path(args.out).write_text(
        "\n".join(u for _, u in good) + ("\n" if good else ""))
    print(f"\nXONG: {len(good)} proxy vao duoc (khong 403) -> {args.out}")
    print(f"  bi 403: {bad403} | dead/loi: {dead} | {time.time()-t0:.0f}s")


if __name__ == "__main__":
    # Windows: SelectorEventLoop tranh loi WinError 10022 cua aiohttp/Proactor
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
