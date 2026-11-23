#!/usr/bin/env python3
"""Assemble the GitHub Pages allowlist and refuse anything outside it.

The site is copied to ``_site`` from ``course-manifest.json``. Only
``index.html``, ``lessons/``, ``reference/``, and ``assets/`` may be
published. Planned lessons must not have files. Relative links inside the
published HTML must resolve to files that are actually published.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "course-manifest.json"
SITE = ROOT / "_site"

UPSTREAM_REPOSITORY = "miuda-ai/active-call"
UPSTREAM_COMMIT = "d453c4f8d4525c9c44fc7c6a8076b9bb98ede123"
UPSTREAM_VERSION = "0.3.120"
BASE_LESSONS_COMMIT = "1eee016a7e82b6151dc3ce54df48337195e34b23"
PUBLISH_ROOTS = ("lessons/", "reference/", "assets/")
SENSITIVE = re.compile(
    r"(?i)("
    r"notion|"
    r"ntn_|"
    r"publication-state|"
    r"\bpage[_ -]?id\b|"
    r"\bNOTES\b|"
    r"\bMISSION\b|"
    r"api[_-]?key|"
    r"secret[_-]?key|"
    r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE|"
    r"AKIA[0-9A-Z]{16}|"
    r"ghp_[A-Za-z0-9]{20,}|"
    r"github_pat_|"
    r"xox[baprs]-|"
    r"sk-ant-|"
    r"sk-or-"
    r")"
)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
SHA = re.compile(r"[0-9a-f]{40}")


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[tuple[str, str]] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value for key, value in attrs}
        if tag == "a" and attr.get("href"):
            self.refs.append(("href", attr["href"]))
        if tag in {"img", "script", "link", "source", "audio", "video"} and attr.get("src"):
            self.refs.append(("src", attr["src"]))
        if tag == "link" and attr.get("href"):
            self.refs.append(("href", attr["href"]))

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_manifest() -> dict:
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {MANIFEST_PATH.name}: {exc}")
    if not isinstance(data, dict):
        fail("manifest must be an object")
    return data


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        fail(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def safe_repo_file(rel: str) -> Path:
    if not isinstance(rel, str) or rel == "" or rel.startswith("/") or "\\" in rel:
        fail(f"unsafe path: {rel!r}")
    parts = Path(rel).parts
    if any(part in {"", ".", ".."} for part in parts):
        fail(f"unsafe path: {rel!r}")
    path = (ROOT / rel).resolve()
    if path != ROOT and ROOT not in path.parents:
        fail(f"path escapes repository: {rel}")
    return path


def publishable(rel: str) -> bool:
    return rel == "index.html" or rel.startswith(PUBLISH_ROOTS)


def check_manifest(data: dict) -> list[dict]:
    upstream = data.get("upstream")
    if not isinstance(upstream, dict):
        fail("upstream must be an object")
    if upstream.get("repository") != UPSTREAM_REPOSITORY:
        fail("upstream repository drifted")
    if upstream.get("commit") != UPSTREAM_COMMIT:
        fail("upstream commit drifted")
    if upstream.get("version") != UPSTREAM_VERSION:
        fail("upstream version drifted")
    if data.get("runtime_verified") is not False:
        fail("runtime_verified must stay false; this course has not been run")

    lessons = data.get("lessons")
    if not isinstance(lessons, list) or len(lessons) != 13:
        fail("manifest must list exactly 13 lessons")
    seen: set[str] = set()
    for index, lesson in enumerate(lessons, start=1):
        if not isinstance(lesson, dict):
            fail(f"lesson {index} must be an object")
        lesson_id = lesson.get("lesson_id")
        if not isinstance(lesson_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", lesson_id):
            fail(f"lesson {index} has an unstable lesson_id")
        if lesson_id in seen:
            fail(f"duplicate lesson_id {lesson_id}")
        seen.add(lesson_id)
        if lesson.get("number") != index:
            fail(f"lesson numbers must be 1..13 in order, got {lesson.get('number')!r} at {index}")
        title = lesson.get("title")
        if not isinstance(title, str) or title.strip() == "":
            fail(f"lesson {lesson_id} needs a title")
        status = lesson.get("status")
        path = lesson.get("path")
        reference = lesson.get("reference_path")
        if status == "readable":
            if not isinstance(path, str) or not publishable(path):
                fail(f"readable lesson {lesson_id} needs a publishable path")
            if reference is not None and (not isinstance(reference, str) or not publishable(reference)):
                fail(f"readable lesson {lesson_id} has a bad reference path")
            if not safe_repo_file(path).is_file():
                fail(f"missing lesson file {path}")
            if isinstance(reference, str) and not safe_repo_file(reference).is_file():
                fail(f"missing reference file {reference}")
        elif status == "planned":
            if path is not None or reference is not None:
                fail(f"planned lesson {lesson_id} must not claim a file")
        else:
            fail(f"lesson {lesson_id} has unknown status {status!r}")
    return lessons


def check_allowlist(data: dict, lessons: list[dict]) -> list[str]:
    allow = data.get("pages_allowlist")
    if not isinstance(allow, list) or not allow:
        fail("pages_allowlist must be a non-empty list")
    if len(allow) != len(set(allow)):
        fail("pages_allowlist contains duplicates")
    if "index.html" not in allow or "assets/style.css" not in allow:
        fail("allowlist must include index.html and assets/style.css")
    for rel in allow:
        if not isinstance(rel, str) or not publishable(rel):
            fail(f"allowlist path is outside the static course: {rel!r}")
        path = safe_repo_file(rel)
        if not path.is_file():
            fail(f"allowlisted file does not exist: {rel}")
        if path.is_symlink():
            fail(f"allowlisted file must not be a symlink: {rel}")

    required = {"index.html", "assets/style.css"}
    for lesson in lessons:
        if lesson["status"] != "readable":
            continue
        required.add(lesson["path"])
        if lesson["reference_path"] is not None:
            required.add(lesson["reference_path"])
    if set(allow) != required:
        missing = sorted(required - set(allow))
        extra = sorted(set(allow) - required)
        fail(f"allowlist does not match readable lessons (missing {missing}, extra {extra})")
    return list(allow)


def scan_text(rel: str, text: str) -> None:
    if SENSITIVE.search(text):
        fail(f"sensitive marker found in {rel}")
    if EMAIL.search(text):
        fail(f"email address found in {rel}")
    if PHONE.search(text):
        fail(f"phone-like number found in {rel}")
    if "index.md" in text:
        fail(f"{rel} still links to index.md")


def parse_html(rel: str) -> LinkParser:
    parser = LinkParser()
    parser.feed(safe_repo_file(rel).read_text(encoding="utf-8"))
    parser.close()
    return parser


def check_html(allow: list[str], lessons: list[dict]) -> None:
    published = set(allow)
    html_files = [rel for rel in allow if rel.endswith(".html")]
    index = parse_html("index.html")
    index_text = "".join(index.text_parts)
    if "已可读" not in index_text or "仅计划" not in index_text:
        fail("index.html must distinguish 已可读 and 仅计划")

    linked: set[str] = set()
    for kind, ref in index.refs:
        if kind != "href" or ref.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = os.path.normpath(ref)
        linked.add(target)

    for lesson in lessons:
        if lesson["title"] not in index_text:
            fail(f"index.html does not mention {lesson['title']}")
        if lesson["status"] == "readable":
            if lesson["path"] not in linked:
                fail(f"index.html does not link to readable lesson {lesson['path']}")
            if lesson["reference_path"] is not None and lesson["reference_path"] not in linked:
                fail(f"index.html does not link to {lesson['reference_path']}")
        elif lesson["path"] is None and any(lesson["lesson_id"] in item for item in linked):
            fail(f"index.html links to a planned lesson id {lesson['lesson_id']}")

    for rel in html_files:
        text = safe_repo_file(rel).read_text(encoding="utf-8")
        scan_text(rel, text)
        if "<audio" in text or "<video" in text or "getUserMedia" in text:
            fail(f"{rel} must not capture or embed audio")
        parser = parse_html(rel)
        base = Path(rel).parent
        for _kind, ref in parser.refs:
            if ref.startswith(("http://", "https://", "mailto:", "#", "data:")):
                if ref.startswith("/") or ref.startswith("http://127.") or ref.startswith("http://localhost"):
                    fail(f"{rel} has a non-portable link {ref}")
                continue
            if ref.startswith("/"):
                fail(f"{rel} uses a site-absolute link {ref}")
            target = os.path.normpath(str(base / ref))
            if target not in published:
                fail(f"{rel} relative link {ref} resolves to unpublished or missing {target}")

    css_rel = "assets/style.css"
    css = safe_repo_file(css_rel).read_text(encoding="utf-8")
    scan_text(css_rel, css)
    if re.search(r"url\(", css):
        fail("assets/style.css must not reference extra files")


def assemble(allow: list[str]) -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    for rel in allow:
        source = safe_repo_file(rel)
        destination = SITE / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    copied = sorted(
        path.relative_to(SITE).as_posix()
        for path in SITE.rglob("*")
        if path.is_file()
    )
    if copied != sorted(allow):
        fail(f"_site contents {copied} do not match allowlist {sorted(allow)}")
    for rel in allow:
        source_hash = hashlib.sha256(safe_repo_file(rel).read_bytes()).hexdigest()
        copied_hash = hashlib.sha256((SITE / rel).read_bytes()).hexdigest()
        if source_hash != copied_hash:
            fail(f"copied {rel} does not match the source file")


def check_content_hashes(data: dict, allow: list[str]) -> None:
    recorded = data.get("pages_sha256")
    if not isinstance(recorded, dict):
        fail("pages_sha256 must map each allowlisted file to its sha256")
    if set(recorded) != set(allow):
        fail("pages_sha256 keys must equal pages_allowlist")
    for rel in allow:
        digest = recorded[rel]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            fail(f"pages_sha256 for {rel} must be a 64-character hex digest")
        actual = hashlib.sha256(safe_repo_file(rel).read_bytes()).hexdigest()
        if actual != digest:
            fail(f"{rel} sha256 does not match pages_sha256")


def git_output(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def blob_at(rev: str, rel: str) -> str | None:
    result = git_output("rev-parse", f"{rev}:{rel}")
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def commit_type(rev: str) -> str | None:
    result = git_output("cat-file", "-t", rev)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def check_lessons_commit(data: dict, allow: list[str], allow_unset: bool) -> None:
    learning = data.get("learning_repo")
    if not isinstance(learning, dict):
        fail("learning_repo must be an object")
    recorded = learning.get("lessons_commit")
    if recorded != BASE_LESSONS_COMMIT:
        fail("lessons_commit must stay the commit that introduced the first three lessons")
    head = git("rev-parse", "HEAD")
    if recorded == head:
        fail("lessons_commit points at HEAD, which would be a self-reference")

    entries = learning.get("content_commits", [])
    if not isinstance(entries, list):
        fail("content_commits must be a list")
    history: dict[str, list[str | None]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            fail("each content_commits entry must be an object")
        commit = entry.get("commit")
        paths = entry.get("paths")
        if commit is not None and (not isinstance(commit, str) or not SHA.fullmatch(commit)):
            fail("content_commits.commit must be a full git commit or null")
        if not isinstance(paths, list) or not paths:
            fail("content_commits.paths must list the files changed in that increment")
        seen_here: set[str] = set()
        for rel in paths:
            if not isinstance(rel, str) or rel not in allow:
                fail(f"content commit path is not allowlisted: {rel!r}")
            if rel in seen_here:
                fail(f"{rel} is repeated inside one content commit")
            seen_here.add(rel)
            history.setdefault(rel, []).append(commit)

    base_type = commit_type(recorded)
    if base_type is None:
        print("lessons_commit is not in this checkout; pages_sha256 still checks the published bytes")
    elif base_type != "commit":
        fail("lessons_commit is not a commit object")
    else:
        for rel in allow:
            base_blob = blob_at(recorded, rel)
            worktree_blob = git("hash-object", rel)
            changed = base_blob != worktree_blob
            if changed and rel not in history:
                fail(f"{rel} no longer matches lessons_commit and is not in content_commits")
            if not changed and rel in history:
                fail(f"{rel} still matches lessons_commit; leave it out of content_commits")

    for rel, commits in history.items():
        worktree_blob = git("hash-object", rel)
        for index, commit in enumerate(commits):
            latest = index == len(commits) - 1
            if commit is None:
                if latest and allow_unset:
                    print(f"{rel} content commit is unset; skipping its git trace")
                    continue
                fail(f"{rel} needs the commit that introduced that version")
            if commit == head:
                fail("content_commits points at HEAD, which would be a self-reference")
            if commit == recorded:
                fail("content_commits must not reuse lessons_commit")
            kind = commit_type(commit)
            if kind is None:
                print(f"content commit for {rel} is not in this checkout; pages_sha256 still checks the bytes")
                continue
            if kind != "commit":
                fail(f"content commit for {rel} is not a commit object")
            recorded_blob = blob_at(commit, rel)
            if recorded_blob is None:
                fail(f"{rel} is missing from content commit {commit}")
            if latest and recorded_blob != worktree_blob:
                fail(f"{rel} does not match its latest content commit {commit}")
            if not latest:
                newer = commits[index + 1]
                if newer is None:
                    continue
                newer_blob = blob_at(newer, rel)
                if newer_blob is not None and newer_blob == recorded_blob:
                    fail(f"{rel} is unchanged between content commits {commit} and {newer}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-unset-lessons-commit",
        action="store_true",
        help="permit a null lessons_commit before the introducing commit exists",
    )
    args = parser.parse_args()
    data = load_manifest()
    lessons = check_manifest(data)
    allow = check_allowlist(data, lessons)
    check_html(allow, lessons)
    assemble(allow)
    check_content_hashes(data, allow)
    check_lessons_commit(data, allow, args.allow_unset_lessons_commit)
    print(f"assembled {len(allow)} allowlisted files into _site")


if __name__ == "__main__":
    main()
