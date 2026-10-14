from . import search
from dotenv import load_dotenv
from github import Github, Auth
from os import environ, getenv
from pathlib import Path
from shutil import rmtree
import base64
import re
import subprocess

# wall-clock kill for clones: a machine-sleep can leave TCP connections
# dead without resets, and a hung clone would otherwise block the sweep
# forever (threads cannot be interrupted)
CLONE_TIMEOUT = 600

def gh_get_user(user):
    try:
        load_dotenv()
        token = getenv("GITHUB_AUTH")
        # unauthenticated access works for public accounts (60 req/hr);
        # a token raises the limit and unlocks private repos
        g = Github(auth=Auth.Token(token)) if token else Github()
        user = g.get_user(user)
    except:
        user = None
    return user

def gh_get_repo_branch(user, repo):
    """Default branch for a single repo, so -r scans get working permalinks."""
    try:
        load_dotenv()
        token = getenv("GITHUB_AUTH")
        g = Github(auth=Auth.Token(token)) if token else Github()
        r = g.get_repo(f"{user}/{repo}")
        return [{"repo_name": repo, "default_branch": r.default_branch}]
    except:
        return []

def gh_get_repos(user):
    g = gh_get_user(user)

    if g is None:
        print(f"[!] Account {user} does not exist (or API rate limit hit; "
              f"set GITHUB_AUTH for a higher limit).")
        return None, None
    
    else:
        repos = gh_get_user(user).get_repos()
        gh_list = list(map(lambda x: {
            "repo_name": x.name, 
            "default_branch": x.default_branch
            }, filter(lambda x: not x.fork and not x.archived, repos)))
        repo_list = list(map(lambda x: x.name, filter(lambda x: not x.fork and not x.archived, repos)))
        return repo_list, gh_list

def clean_git(path):
    git_ignore = f"{path}/.gitignore"
    dot_git = f"{path}/.git"
    if Path(git_ignore).exists():
        Path(git_ignore).unlink()
    if Path(dot_git).exists():
        rmtree(dot_git)

def cli_gh_clone_repo(user, repo):
    path = f"/tmp/.supplyshark/{user}/{repo}"
    load_dotenv()
    token = getenv("GITHUB_AUTH")
    try:
        cmd = ["git", "clone", "--depth", "1", "--single-branch", "--quiet",
               f"https://github.com/{user}/{repo}.git", path]
        if token:
            # token via http header: keeps it out of URLs and process lists
            creds = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            cmd = ["git",
                   "-c", f"http.https://github.com/.extraheader=Authorization: Basic {creds}",
                   *cmd[1:]]
        subprocess.run(cmd, check=True, capture_output=True, timeout=CLONE_TIMEOUT)
        clean_git(path)
        search.get_packages(path, user, repo)
        rmtree(path)
    except subprocess.TimeoutExpired:
        print(f"[!] Clone of {user}/{repo} timed out after {CLONE_TIMEOUT}s; skipping")
        rmtree(path, ignore_errors=True)
    except Exception as e:
        print(f"[!] Failed to clone {user}/{repo} "
              f"({'private or missing without a GITHUB_AUTH token' if not token else type(e).__name__})")

def return_user(value):
    if re.compile(r"[A-Za-z0-9]+/([A-Za-z0-9]+)", re.IGNORECASE).match(value):
        user = value.split("/")[0]
    elif re.compile(r"github:[A-Za-z0-9]+/[A-Za-z0-9]+", re.IGNORECASE).match(value):
        user = value.split(":")[1].split("/")[0]
    elif re.compile(r"[A-Za-z0-9]+\+[A-Za-z0-9]+://[A-Za-z0-9]+@[A-Za-z0-9]+\.[A-Za-z0-9]+(:|/)[A-Za-z0-9]+/[A-Za-z0-9]+", re.IGNORECASE).match(value):
        pre = value.split("@")[1]
        if ":" in pre:
            user = value.split(":")[2].split("/")[0]
        else:
            user = pre.split("/")[1]
    elif re.compile(r"git://[A-Za-z0-9]+\.[A-Za-z0-9]+/[A-Za-z0-9]+/[A-Za-z0-9]+", re.IGNORECASE).match(value):
        user = value.split("/")[3]
    else:
        user = ""
    return user

def return_user_regular(value):
    pattern = re.compile(r"github\.com/(.*?)/+", re.IGNORECASE)
    user = pattern.findall(value)[0]
    return user
