#! /usr/bin/python3

import yaml
import sys, os
import subprocess
import tempfile

deps = {}
resolved = set()

tested = set()
installed = set()

def run_ansible(task, depth):
    tmp = tempfile.NamedTemporaryFile("w+", dir=os.getcwd(), delete=False)

    play = [
        dict(name=f"Run { task['name']}",
             connection="local",
             gather_facts=False,
             hosts="localhost",
             tasks=task["spec"],
             )
    ]

    yaml.dump(play, tmp)
    tmp.close()

    print("-"*(depth+2))
    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = "/home/kevin/openshift/ci-artifacts/config/ansible.cfg"
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        proc = subprocess.run(["/usr/bin/ansible-playbook", tmp.name],
                              env=env, stdin=None)

        ret = proc.returncode
    finally:
        os.remove(tmp.name)
        pass
    print("-"*(depth+2))

    return ret == 0

    pass

def run_shell(task, depth):
    cmd = task["spec"]
    print(" "*depth, f"|>SHELL<| \n{cmd.strip()}")

    print("-"*(depth+2))
    sys.stdout.flush()
    sys.stderr.flush()
    proc = subprocess.run(["/bin/bash", "-c", cmd], stdin=subprocess.PIPE)
    ret = proc.returncode
    print("-"*(depth+2))

    return ret == 0

def run(task, depth):
    print(" "*depth, f"|Running '{task['name']}' ...")
    type_ = task["type"]
    if type_ == "shell":
        success = run_shell(task, depth)
    elif type_ == "ansible":
        success = run_ansible(task, depth)
    else:
        print(f"ERROR: unknown task type: {type_}.")
        sys.exit(1)

    print(" "*depth, f"|Running '{task['name']}':", "Success" if success else "Failure")
    print(" "*depth, f"|___")
    return success


def do_test(dep, depth, print_first_test=True):
    if not dep["spec"].get("tests"):
        if print_first_test:
            print(f"Nothing to test for '{dep['name']}'")
        return True

    for task in dep["spec"].get("tests", []):
        if print_first_test:
            print(" "*depth, f"Testing '{dep['name']}' ...")
            print_first_test = False

        tested.add(f"{dep['name']} -> {task['name']}")
        success = run(task, depth)
        if success:
            return True

    return False


def resolve(dep, depth=0):
    print(" "*depth, f"Treating '{dep['name']}' dependency ...")

    if dep['name'] in resolved:
        print(" "*depth, f"Dependency '{dep['name']}' has already need resolved, skipping.")
        return

    for req in dep["spec"].get("requirements", []):
        print(" "*depth, f"Dependency '{dep['name']}' needs '{req}' ...")
        try:
            next_dep = deps[req]
        except KeyError as e:
            print(f"ERROR: missing dependency: {req}")
            sys.exit(1)
        resolve(next_dep, depth=depth+1)

        print(" "*depth, f"Nothing to test for '{dep['name']}'.")

    if do_test(dep, depth):
        print(" "*depth, f"Dependency '{dep['name']}' is satisfied, no need to install.")

    else:
        first_install = True
        for task in dep["spec"].get("install", []):
            if first_install:
                first_install = False
                print(" "*depth, f"Installing '{dep['name']}' ...")

            if not run(task, depth):
                print(f"ERROR: install of '{dep['name']}' failed.")
                sys.exit(1)

            installed.add(f"{dep['name']} -> {task['name']}")

        if first_install:
            # no install task available

            print(f"ERROR: '{dep['name']}' test failed, but no install script provided.")
            sys.exit(1)

        if not do_test(dep, depth, print_first_test=False):
            print(f"ERROR: '{dep['name']}' installed, but test still failing.")
            sys.exit(1)


    resolved.add(dep['name'])
    print(" "*depth, f"Done with {dep['name']}.")

def main():
    with open(sys.argv[1]) as f:
        docs = list(yaml.safe_load_all(f))

    for doc in docs:
        deps[doc["name"]] = doc

    try:
        entrypoint = sys.argv[2]
    except IndexError:
        entrypoint = docs[0]["name"]

    resolve(deps[entrypoint])
    print("All done.")

    print("Tested:")
    [print(f"- {t}") for t in tested]
    if installed:
        print("Installed:")
        [print(f"- {t}") for t in installed]
    else:
        print("Installed: nothing.")

if __name__ == "__main__":
    main()
