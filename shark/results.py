from colorama import Fore
from . import surfaces
import json

def get_branch(repo_name, repos):
    for repo in repos:
        if repo['repo_name'] == repo_name:
            return repo['default_branch']
    return None

def _label(base, tag):
    return f"{base}:{tag}" if tag else base

def _write_result(label, item, repo_urls, bug_urls, output_file):
    msg = f"[{label}] {item} {list(set(repo_urls))} {list(set(bug_urls))}"
    print(f"{Fore.CYAN}{msg}{Fore.RESET}")
    with open(output_file, "a") as f:
        print(msg, file=f)

def npm_results(npm_data, repos, output_file="results.txt"):
    npm_package_results = npm_data["package_results"]
    npm_scope_results = npm_data["scope_results"]
    count = 0

    for package_result in npm_package_results:
        try:
            package = package_result[0]["package"]
            bug_urls = []
            repo_urls = []
            for i in range(1, len(package_result)):
                file = package_result[i][0]["file"]
                line_number = package_result[i][0]['line_number']
                repo = "/".join(file.split("/")[:2])
                branch = get_branch(repo.split("/")[1], repos)
                repo_url = f"https://github.com/{repo}"
                file_path = "/".join(file.split("/")[2:])
                bug_url = f"{repo_url}/blob/{branch}/{file_path}?plain=1#L{line_number}"
                bug_urls.append(bug_url)
                repo_urls.append(repo_url)

            # cap ref lists: a name hit in a big org cites hundreds of
            # files; ten permalinks is enough to act on
            bug_urls = list(dict.fromkeys(bug_urls))[:10]
            repo_urls = list(dict.fromkeys(repo_urls))[:10]
            ref_files = [package_result[i][0]["file"] for i in range(1, len(package_result))]
            label = _label("npm", surfaces.package_surface(ref_files))
            exec_tag = package_result[0].get("exec")
            if exec_tag:
                label += f":{exec_tag}"
            _write_result(label, package, repo_urls, bug_urls, output_file)
            count += 1
        except:
            pass

    for scope_result in npm_scope_results:
        try:
            scope = scope_result[0]["scope"]
            packages = scope_result[0].get("packages") or []
            item = scope
            if packages:
                item += f" (packages: {', '.join(packages)})"
            if scope_result[0].get("unverified"):
                item += " [scope ownership unverified]"
            bug_urls = []
            repo_urls = []
            for i in range(1, len(scope_result)):
                file = scope_result[i][0]["file"]
                line_number = scope_result[i][0]['line_number']
                repo = "/".join(file.split("/")[:2])
                branch = get_branch(repo.split("/")[1], repos)
                repo_url = f"https://github.com/{repo}"
                file_path = "/".join(file.split("/")[2:])
                bug_url = f"{repo_url}/blob/{branch}/{file_path}?plain=1#L{line_number}"
                bug_urls.append(bug_url)
                repo_urls.append(repo_url)

            _write_result("npm scope", item, list(set(repo_urls))[:10], bug_urls, output_file)
            count += 1
        except:
            pass
    
    return count

def gem_results(gem_data, repos, output_file="results.txt"):
    gem_package_results = gem_data['package_results']
    count = 0

    for package_result in gem_package_results:
        try:
            package = package_result[0]["package"]
            bug_urls = []
            repo_urls = []
            for i in range(1, len(package_result)):
                file = package_result[i][0]["file"]
                line_number = package_result[i][0]['line_number']
                repo = "/".join(file.split("/")[:2])
                repo_url = f"https://github.com/{repo}"
                branch = get_branch(repo.split("/")[1], repos)
                file_path = "/".join(file.split("/")[2:])
                bug_url = f"{repo_url}/blob/{branch}/{file_path}?plain=1#L{line_number}"
                bug_urls.append(bug_url)
                repo_urls.append(repo_url)

            # cap ref lists: a name hit in a big org cites hundreds of
            # files; ten permalinks is enough to act on
            bug_urls = list(dict.fromkeys(bug_urls))[:10]
            repo_urls = list(dict.fromkeys(repo_urls))[:10]
            ref_files = [package_result[i][0]["file"] for i in range(1, len(package_result))]
            _write_result(_label("gem", surfaces.package_surface(ref_files)), package, repo_urls, bug_urls, output_file)
            count += 1
        except:
            pass
    
    return count

def pip_results(pip_data, repos, output_file="results.txt"):
    pip_package_results = pip_data['package_results']
    count = 0

    for package_result in pip_package_results:
        try:
            bug_urls = []
            repo_urls = []
            package = package_result[0]["package"]
            for i in range(1, len(package_result)):
                file = package_result[i][0]["file"]
                line_number = package_result[i][0]['line_number']
                repo = "/".join(file.split("/")[:2])
                branch = get_branch(repo.split("/")[1], repos)
                repo_url = f"https://github.com/{repo}"
                file_path = "/".join(file.split("/")[2:])
                bug_url = f"{repo_url}/blob/{branch}/{file_path}?plain=1#L{line_number}"
                bug_urls.append(bug_url)
                repo_urls.append(repo_url)

            # cap ref lists: a name hit in a big org cites hundreds of
            # files; ten permalinks is enough to act on
            bug_urls = list(dict.fromkeys(bug_urls))[:10]
            repo_urls = list(dict.fromkeys(repo_urls))[:10]
            ref_files = [package_result[i][0]["file"] for i in range(1, len(package_result))]
            _write_result(_label("pip", surfaces.package_surface(ref_files)), package, repo_urls, bug_urls, output_file)
            count += 1
        except:
            pass
    
    return count

def mcp_url_results(items, repos, output_file="results.txt"):
    """Remote MCP server endpoints from agent configs: plaintext HTTP or
    domains that no longer resolve (re-registration = agent connection
    takeover)."""
    count = 0
    for item in items:
        try:
            url = item[0]["url"]
            reason = item[0]["reason"]
            repo_urls = []
            bug_urls = []
            for i in range(1, len(item)):
                file = item[i][0]["file"]
                line_number = item[i][0]["line_number"]
                repo = "/".join(file.split("/")[:2])
                branch = get_branch(repo.split("/")[1], repos)
                repo_url = f"https://github.com/{repo}"
                file_path = "/".join(file.split("/")[2:])
                bug_urls.append(f"{repo_url}/blob/{branch}/{file_path}?plain=1#L{line_number}")
                repo_urls.append(repo_url)

            # cap ref lists: endpoints/domains can be referenced hundreds of times
            shown = list(set(bug_urls))
            _write_result("mcp-url", f"{reason} {url} ({len(shown)} refs)", list(set(repo_urls)), shown[:10], output_file)
            count += 1
        except:
            pass

    return count

def url_results(items, repos, output_file="results.txt"):
    """Dead or internal-only domains referenced by the scanned repos.
    Domains have no reservation system: an expired one is claimable, and
    re-registration captures every URL still pointing at it."""
    count = 0
    for item in items:
        try:
            host = item[0]["host"]
            reason = item[0]["reason"]
            repo_urls = []
            bug_urls = []
            for i in range(1, len(item)):
                file = item[i][0]["file"]
                line_number = item[i][0]["line_number"]
                repo = "/".join(file.split("/")[:2])
                branch = get_branch(repo.split("/")[1], repos)
                repo_url = f"https://github.com/{repo}"
                file_path = "/".join(file.split("/")[2:])
                bug_urls.append(f"{repo_url}/blob/{branch}/{file_path}?plain=1#L{line_number}")
                repo_urls.append(repo_url)

            # cap ref lists: dead domains can be referenced hundreds of times
            shown = list(set(bug_urls))
            _write_result("domain", f"{reason} {host} ({len(shown)} refs)", list(set(repo_urls)), shown[:10], output_file)
            count += 1
        except:
            pass

    return count

def process_results(results, repos, output_file="results.txt"):
    data = json.loads(results)

    counts = [
        npm_results(data.get('npm_results') or {"package_results": [], "scope_results": []},
                    repos, output_file),
        gem_results(data.get('gem_results') or {"package_results": []}, repos, output_file),
        pip_results(data.get('pip_results') or {"package_results": []}, repos, output_file),
        mcp_url_results(data.get('mcp_url_results', []), repos, output_file),
        url_results(data.get('url_results', []), repos, output_file),
    ]
    return sum(counts)
