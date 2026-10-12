from colorama import Fore
from pathlib import Path
from shutil import rmtree
from sys import exit
import argparse
import asyncio
import json
import shark

info_msg = f"[{Fore.LIGHTBLUE_EX}*{Fore.RESET}]"
found_msg = f"[{Fore.LIGHTGREEN_EX}+{Fore.RESET}]"
no_msg = f"[{Fore.LIGHTRED_EX}-{Fore.RESET}]"

def found_fmt(total):
    return f"{Fore.LIGHTGREEN_EX}{total}{Fore.RESET}"

async def npm(copy_dir, sem, super_sem):
    async with sem:
        newlist = await shark.npm.find_package_json(copy_dir)

    package_list = list(set(newlist + shark.npm.read_npm_search_json(copy_dir)))

    # scoped names short-circuit at the scope level: one verdict per scope,
    # taken => nothing under it is claimable, available => one finding
    # covers every package under it
    unscoped = sorted(p for p in package_list if not p.startswith("@"))
    by_scope = {}
    for package in package_list:
        if package.startswith("@") and "/" in package and not package.startswith("@@"):
            by_scope.setdefault(package.split("/")[0], []).append(package)

    if len(unscoped) == 1:
        package_msg = "package."
    else:
        package_msg = "packages."

    print(f"{info_msg} Scanning {len(unscoped)} npm {package_msg}")

    async with super_sem:
        package_results = await asyncio.gather(*[
            shark.npm.scan_packages(copy_dir, package)
            for package in unscoped
        ])
        package_results = [result for result in package_results if result is not None and result]

    total_package_results = len(package_results)

    if total_package_results == 0:
        print(f"{no_msg} Found no available npm packages.")
    else:
        total_package_results_fmt = found_fmt(total_package_results)
        print(f"{found_msg} Found {total_package_results_fmt} available npm "
              f"{'package.' if total_package_results == 1 else 'packages.'}")

    scope_list = sorted(by_scope)

    if len(scope_list) == 1:
        scope_msg = "scope."
    else:
        scope_msg = "scopes."

    print(f"{info_msg} Scanning {len(scope_list)} npm {scope_msg}")

    async with super_sem:
        scope_results = await asyncio.gather(*[
            shark.npm.scope_check(copy_dir, scope, packages)
            for scope, packages in by_scope.items()
        ])
        scope_results = [result for result in scope_results if result is not None and result]

    total_scope_results = len(scope_results)

    if total_scope_results == 0:
        print(f"{no_msg} Found no available npm scopes.")
    else:
        total_scope_results_fmt = found_fmt(total_scope_results)
        print(f"{found_msg} Found {total_scope_results_fmt} available "
              f"{'scope.' if total_scope_results == 1 else 'scopes.'}")

    print(f"{info_msg} npm scan complete.")

    results = {
        "package_results": package_results,
        "scope_results": scope_results
    }

    return {"npm_results": results}


async def gem(copy_dir, super_sem):
    gem_list = list(set(shark.gem.read_gem_search_json(copy_dir)))

    if len(gem_list) == 1:
        gem_msg = "gem."
    else:
        gem_msg = "gems."

    print(f"{info_msg} Scanning {len(gem_list)} {gem_msg}")

    async with super_sem:
        package_results = await asyncio.gather(*[
            shark.gem.scan_gems(copy_dir, gem)
            for gem in gem_list
        ])
        if package_results:
            package_results = [result for result in package_results if result is not None and result]
    
    total_gem_results = len(package_results)

    if total_gem_results == 0:
        print(f"{no_msg} Found no available gems.")
    else:
        total_gem_results_fmt = found_fmt(total_gem_results)

        if total_gem_results == 1:
            gem_msg = "gem."
        else:
            gem_msg = "gems."

        print(f"{found_msg} Found {total_gem_results_fmt} available {gem_msg}")

    print(f"{info_msg} gem scan complete.")

    results = {
        "package_results": package_results
    }

    return {"gem_results": results}

async def pip(copy_dir, sem, super_sem):
    async with sem:
        piplist = await shark.pip.find_requirements_txt(copy_dir)
        pyproject_list = shark.pip.find_pyproject_toml(copy_dir)

    pip_list = list(set(piplist + pyproject_list + shark.pip.read_pip_search_json(copy_dir)))

    if len(pip_list) == 1:
        pip_msg = "package."
    else:
        pip_msg = "packages."

    print(f"{info_msg} Scanning {len(pip_list)} python {pip_msg}")

    async with super_sem:
        package_results = await asyncio.gather(*[
            shark.pip.scan_packages(copy_dir, package)
            for package in pip_list
        ])
        package_results = [result for result in package_results if result is not None and result]
    
    total_pip_results = len(package_results)

    if total_pip_results == 0:
        print(f"{no_msg} Found no available python packages.")
    else:
        total_pip_results_fmt = found_fmt(total_pip_results)
        
        if total_pip_results == 1:
            pip_msg = "package."
        else:
            pip_msg = "packages."

        print(f"{found_msg} Found {total_pip_results_fmt} available python {pip_msg}")

    print(f"{info_msg} pip scan complete.")

    results = {
        "package_results": package_results
    }

    return {"pip_results": results}

def cleanup(copy_dir, tmp):
    # ignore_errors: a second scanner instance (or a wiped /tmp) may have
    # already removed these; cleanup must never kill a sweep
    rmtree(copy_dir, ignore_errors=True)
    rmtree(tmp, ignore_errors=True)

def create_dir(account):
    tmp = f"/tmp/.supplyshark/{account}"
    copy_dir = f"/tmp/.supplyshark/_output/{account}"
    Path(tmp).mkdir(parents=True, exist_ok=True)
    Path(copy_dir).mkdir(parents=True, exist_ok=True)
    return tmp, copy_dir

async def start_cli(account, repo):
    tmp, copy_dir = create_dir(account)

    sem = asyncio.Semaphore(10)
    super_sem = asyncio.Semaphore(50)

    if repo:
        repo_queue = [repo]
        gh_check = shark.github.gh_get_repo_branch(account, repo)
    else:
        repo_queue, gh_check = shark.github.gh_get_repos(account)
    
    if not repo_queue:
        print(f"{no_msg} No repositories found.")
        cleanup(copy_dir, tmp)
        return None, None
    
    if len(repo_queue) == 1:
        repo_msg = "repository."
    else:
        repo_msg = "repositories."

    print(f"{info_msg} Scanning {len(repo_queue)} {repo_msg}")

    async with sem:
        await asyncio.gather(*[
            asyncio.to_thread(shark.github.cli_gh_clone_repo, account, repo)
            for repo in repo_queue
        ])

    try:
        npm_results, gem_results, pip_results, mcp_url_results, url_results = await asyncio.gather(
            npm(copy_dir, sem, super_sem),
            gem(copy_dir, super_sem),
            pip(copy_dir, sem, super_sem),
            shark.search.mcp_url_findings(copy_dir),
            shark.search.url_findings(copy_dir)
        )
    finally:
        await shark.registry.close()

    for label, items, noun in (
        ("MCP endpoint", mcp_url_results, "findings"),
        ("dead-domain", url_results, "findings"),
    ):
        if items:
            print(f"{found_msg} Found {found_fmt(len(items))} {label} {noun}.")
        else:
            print(f"{no_msg} Found no {label} {noun}.")

    data = {
        "npm_results": npm_results["npm_results"],
        "gem_results": gem_results["gem_results"],
        "pip_results": pip_results["pip_results"],
        "mcp_url_results": mcp_url_results,
        "url_results": url_results
    }

    cleanup(copy_dir, tmp)

    return json.dumps(data, indent=2), gh_check

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", type=str)
    parser.add_argument("-l", type=str)
    parser.add_argument('-r', type=str)
    args = parser.parse_args()

    if args.u is not None:
        print(f"{info_msg} Scanning account {args.u}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            results, gh_check = asyncio.run(start_cli(args.u, args.r))
        except KeyboardInterrupt:
            pass
        
        if results:
            total = shark.results.process_results(results, gh_check)
            print(f"{found_msg} Wrote {found_fmt(total)} findings to results.txt")
    elif args.l is not None:
        grand_total = 0
        accounts = 0
        with open(args.l, 'r') as f:
            for u in f.readlines():
                account = u.strip()
                if not account:
                    continue
                print(f"{info_msg} Scanning account {account}")
                accounts += 1
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    results, gh_check = asyncio.run(start_cli(account, None))
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(f"[!] Account {account} failed ({type(e).__name__}: {e}); continuing.")
                    results = None

                if results:
                    grand_total += shark.results.process_results(results, gh_check)

        print(f"{found_msg} Scanned {found_fmt(accounts)} accounts; "
              f"wrote {found_fmt(grand_total)} findings to results.txt")
    else:
        print(f"{no_msg} Please specify -u or -l")
        exit(0)
