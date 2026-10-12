import re

def check(result):
    if len(result.split()) > 1:
        return False
    else:
        return True

# npx/bunx/uvx/dlx take the package as their first argument and may be
# followed by extra arguments, so the single-token rule does not apply
RUNNERS = {'npx', 'bunx', 'uvx', 'dlx'}

def search(lines):
    matches = []
    pattern = re.compile(r'(install|add|ci|i|npx|bunx|uvx|dlx)(?: -(?:y|g|D|E|U|s|q)| --(?:save-dev|save-optional|save-exact|save-prod|save|dev|global|upgrade|yes|silent|quiet))? (.+)')
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        if match.group(1) in RUNNERS:
            matches += [package(match.group(2).split()[0])]
        elif check(match.group(2)):
            matches += [package(match.group(2))]
    return matches

def gem_search(gemlist):
    matches = []
    badlines = ['igem ',
                'agem ',
                'egem ',
                '_gem ',
                ', git',
                ', path',
                ', github',
                'github.com',
                'rails-assets.org']
    
    pattern = re.compile(r"gem (i |install |\'|\")(.*)")
    for gem in gemlist:
        if not any(badline in gem for badline in badlines):
            match = pattern.search(gem)
            if match:
                matches += [package_gem(match.group(2))]
    return matches

def package(line):
    for ch in ['"', "'", "`", ";", ",", "}", "+", ")", "("]:
        if ch in line:
            line = line.replace(ch, "")
    
    line = line.split(">")[0].split("=")[0].split("<")[0]
    line = line.split("\\")[0].split("~")[0]

    # strip @version specifiers: @scope/pkg@2.5 -> @scope/pkg, foo@1.2 -> foo
    # (the versioned spelling 404s on the registry and reads as a takeover)
    if line.count("@") > 1:
        line = line[:line.rindex("@")]
    elif "@" in line and line[0] != "@":
        line = line.split("@")[0]

    if line.endswith("."):
        line = line[:-1]
    if line.startswith("."):
        line = ""
    
    if line.endswith("-"):
        line = ""

    if line.startswith(" "):
        line = line[1:]
    
    line = line.split(" ")[0]

    # flag arguments (pip -r requirements.txt, -t /target/dir) and stray
    # prose that looks like a filename are not package names
    if re.search(r'\.(txt|toml|ya?ml|json|lock|sh|md|py|js|ts|cfg|ini)$', line):
        line = ""

    if "/" in line and not line.startswith("@"):
        line = ""

    if "%" in line:
        line = ""
    elif "*" in line:
        line = ""
    elif line.startswith("https://"):
        line = ""
    elif line == "PATH_TO_TARBALL":
        line = ""
    elif line == "any-required-dependencies":
        line = ""
    elif line == "previously":
        line = ""
    elif line == "*":
        line = ""
    elif line.startswith("{"):
        line = ""
    elif "does-not-exist" in line:
        line = ""
    elif line == "ended":
        line = ""

    if "dependecies" in line:
        line = ""
    
    line = line.split("[")[0]

    if line == "Yarn":
        line = ""
    
    if line.endswith("."):
        line = line[:-1]

    if "@x.y.z" in line:
        line = ""
    
    if line == "failed!":
        line = ""
    
    if line == "!!!":
        line = ""

    if line.endswith("."):
        line = line[:-1]
    
    line = line.lower().rstrip()

    if line == "sission":
        line = ""
    
    if "does-not-exist" in line:
        line = ""

    pattern = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+", re.IGNORECASE)
    if pattern.match(line):
        line = ""
    
    pattern2 = re.compile(r"[0-9]+\.[0-9]+s", re.IGNORECASE)
    if pattern2.match(line):
        line = ""
    
    if line != "":
        if not (line[0].isalnum() or line[0] == '@'):
            line = ""

    if line == "node_modules":
        line = ""

    return line

def package_gem(gem):
    for ch in ['"', "'", "`", "{", "}"]:
        if ch in gem:
            gem = gem.replace(ch, "")
    
    gem = gem.split(",")[0].split(":")[0].split("\\")[0]
    gem = gem.split("/")[0].split(" ")[0].split("#")[0]
    gem = gem.split("<")[0].split(";")[0].split("&rsquo;")[0]

    if gem.endswith(".gem"):
        gem = ""
    elif gem.startswith("."):
        gem = ""
    elif gem.endswith("."):
        gem = gem[:-1]
    elif gem.startswith("$"):
        gem = ""
    elif gem.endswith("-"):
        gem = ""
    elif "(" in gem:
        gem = ""
    elif "%" in gem:
        gem = ""
    
    return gem