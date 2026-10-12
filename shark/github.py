from . import search
from dotenv import load_dotenv
from github import Github, Auth
from os import getenv
from pathlib import Path
from shutil import rmtree
import pygit2
import re

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
    auth_method = "x-access-token"
    token = getenv("GITHUB_AUTH")
    try:
        if token:
            callbacks = pygit2.RemoteCallbacks(pygit2.UserPass(auth_method, token))
            pygit2.clone_repository(f"https://github.com/{user}/{repo}.git", path, callbacks=callbacks)
        else:
            pygit2.clone_repository(f"https://github.com/{user}/{repo}.git", path)
        clean_git(path)
        search.get_packages(path, user, repo)
        rmtree(path)
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
