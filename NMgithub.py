#!/usr/bin/env python3
import os
import sys
import hashlib
from pathlib import Path
from dotenv import load_dotenv
import git
from github import Github, GithubException, Auth
load_dotenv()

GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
REPO_NAME      = os.getenv("GITHUB_REPO_NAME", "lab5-netman")
LOCAL_DIR      = Path(__file__).parent.resolve()
COMMIT_AUTHOR  = os.getenv("GIT_AUTHOR_NAME",  "Ethan")
COMMIT_EMAIL   = os.getenv("GIT_AUTHOR_EMAIL")

# These files are always pushed regardless of whether they changed
TARGET_FILES = ["snmp_data.txt", "cpu_utilization.jpg"]

SKIP_DIRS  = {".git", "__pycache__", "venv"}
SKIP_FILES = {".env", "sshInfo.json"}


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_blob(blob_bytes: bytes) -> str:
    return hashlib.sha256(blob_bytes).hexdigest()


def collect_target_files() -> list[Path]:
    """Return the explicitly named target files that exist on disk."""
    files = []
    for name in TARGET_FILES:
        p = LOCAL_DIR / name
        if p.exists():
            files.append(p)
        else:
            print(f"Warning: target file not found: {name}")
    return files


def collect_all_repo_files(exclude: set[Path]) -> list[Path]:
    """Return every trackable file in the repo directory, minus the exclusion set."""
    files = []
    for path in LOCAL_DIR.rglob("*"):
        if not path.is_file():
            continue
        # Skip anything inside a blacklisted directory
        if any(part in SKIP_DIRS for part in path.relative_to(LOCAL_DIR).parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if path not in exclude:
            files.append(path)
    return sorted(files)


def get_or_create_github_repo(gh: Github, repo_name: str):
    user = gh.get_user()
    try:
        repo = user.get_repo(repo_name)
        print(f"Using existing repository: {repo.html_url}")
    except GithubException as exc:
        if exc.status != 404:
            raise
        print(f"Repository '{repo_name}' not found - creating it...")
        repo = user.create_repo(
            repo_name,
            description="Lab 5 - Network Management files",
            private=False,
            auto_init=True,
        )
        print(f"Created repository: {repo.html_url}")
    return repo


def get_or_init_local_repo(local_dir: Path, remote_url: str) -> git.Repo:
    git_dir = local_dir / ".git"
    if git_dir.exists():
        repo = git.Repo(local_dir)
        print(f"Using existing local repository at {local_dir}")
    else:
        repo = git.Repo.init(local_dir)
        print(f"Initialised new local repository at {local_dir}")

    with repo.config_writer() as cfg:
        cfg.set_value("user", "name",  COMMIT_AUTHOR)
        cfg.set_value("user", "email", COMMIT_EMAIL)

    try:
        origin = repo.remote("origin")
        if origin.url != remote_url:
            origin.set_url(remote_url)
            print("Updated remote 'origin' URL")
        else:
            print("Remote 'origin' already set")
    except ValueError:
        repo.create_remote("origin", remote_url)
        print("Added remote 'origin'")

    return repo


def sync_from_remote(repo: git.Repo):
    try:
        repo.remote("origin").fetch()
        print("Fetched remote state.")
    except git.GitCommandError:
        print("Remote has no commits yet - skipping fetch.")


def _push(repo: git.Repo):
    origin = repo.remote("origin")

    try:
        if repo.active_branch.name == "master":
            repo.head.reference.rename("main")
    except TypeError:
        pass

    ref = "main"

    # Merge any existing remote commits (e.g. auto-init README) so the push
    # is always a fast-forward and is not rejected as non-fast-forward.
    remote_heads = [r.remote_head for r in origin.refs]
    if ref in remote_heads:
        try:
            repo.git.merge(f"origin/{ref}", "--allow-unrelated-histories", "--no-edit")
        except git.GitCommandError:
            pass

    print(f"Pushing to origin/{ref}...")
    try:
        push_info = origin.push(refspec=f"HEAD:refs/heads/{ref}", set_upstream=True)
        for info in push_info:
            if info.flags & git.PushInfo.ERROR:
                print(f"Push error: {info.summary}")
            else:
                print(f"Push OK -> origin/{ref}")
    except git.GitCommandError as exc:
        print(f"Push failed: {exc}")
        sys.exit(1)


def push_target_files(repo: git.Repo, target_files: list[Path]):
    """Always stage and push the explicitly listed target files."""
    if not target_files:
        print("No target files found - nothing to push.")
        return

    relative_paths = [str(f.relative_to(LOCAL_DIR)) for f in target_files]
    print(f"Staging target files: {relative_paths}")
    repo.index.add(relative_paths)

    has_changes = not repo.head.is_valid() or bool(repo.index.diff("HEAD")) or repo.is_dirty(index=True)
    if has_changes:
        commit = repo.index.commit(
            "Update target .txt and .jpg files",
            author=git.Actor(COMMIT_AUTHOR, COMMIT_EMAIL),
            committer=git.Actor(COMMIT_AUTHOR, COMMIT_EMAIL),
        )
        print(f"Committed: {commit.hexsha[:8]} - {commit.message.strip()}")
    else:
        print("Target files unchanged - skipping commit.")

    _push(repo)


def push_modified_files(repo: git.Repo, gh_repo, other_files: list[Path]):
    """Compare every other repo file against GitHub and push only what changed."""
    if not other_files:
        print("No other files to compare.")
        return

    print("Comparing remaining repo files against remote...")
    modified = []

    for local_path in other_files:
        rel = str(local_path.relative_to(LOCAL_DIR))
        local_hash = sha256_of_file(local_path)

        try:
            content = gh_repo.get_contents(rel)
            remote_hash = sha256_of_blob(content.decoded_content)
            if local_hash != remote_hash:
                print(f"  MODIFIED  {rel}")
                modified.append(rel)
            else:
                print(f"  unchanged {rel}")
        except GithubException as exc:
            if exc.status == 404:
                print(f"  NEW       {rel}")
                modified.append(rel)
            else:
                raise

    if not modified:
        print("All other files are up-to-date. Nothing to push.")
        return

    print(f"Staging {len(modified)} modified/new file(s): {modified}")
    repo.index.add(modified)

    commit = repo.index.commit(
        f"Update {len(modified)} modified file(s)",
        author=git.Actor(COMMIT_AUTHOR, COMMIT_EMAIL),
        committer=git.Actor(COMMIT_AUTHOR, COMMIT_EMAIL),
    )
    print(f"Committed: {commit.hexsha[:8]} - {commit.message.strip()}")
    _push(repo)


def main():
    auth = Auth.Token(GITHUB_TOKEN)
    gh   = Github(auth=auth)
    try:
        user = gh.get_user()
        print(f"Authenticated as: {user.login}")
    except GithubException as exc:
        print(f"Authentication failed: {exc}")
        sys.exit(1)

    gh_repo    = get_or_create_github_repo(gh, REPO_NAME)
    remote_url = gh_repo.clone_url.replace(
        "https://", f"https://{GITHUB_TOKEN}@"
    )

    local_repo = get_or_init_local_repo(LOCAL_DIR, remote_url)
    sync_from_remote(local_repo)

    # Step 1: always push the named target files
    target_files = collect_target_files()
    print(f"\nStep 1: Push target files")
    push_target_files(local_repo, target_files)

    # Step 2: compare everything else and push modified files
    other_files = collect_all_repo_files(exclude=set(target_files))
    print(f"\nStep 2: Push modified repo files")
    push_modified_files(local_repo, gh_repo, other_files)

    print(f"\nDone. Repository: {gh_repo.html_url}")
    gh.close()


if __name__ == "__main__":
    main()
