#!/usr/bin/env python
import sys, os, json, traceback
from datetime import datetime
from subprocess import Popen, PIPE

from code_sitter_cmd import build_recipe_C, build_recipe_SM, subcommand

# services is implicitely used for below list of users:
services_users = ["kernelC", "kernelSM"]

def main(config_file, test_file=None, end_cleaning=True):
    current_path = os.getcwd()
    tests=None

    try:
        fp = open(config_file)
        jsconfig = json.load(fp)
        fp.close()
    except Exception as e:
        print "Unable to read configuration file '%s': %s\n"%(config_file, str(e))
        sys.exit(-1)

    try:
        config = jsconfig['config']
        projects = jsconfig['projects']
        repo_path = config['repo-path']

        now = datetime.now()
        print "\n *** Compilation Test: %s ***\n"%(str(now))

        if repo_path != 'none':
            cleaning(current_path, repo_path, projects)

            print "\nCloning projects:"
            for project in projects:
                r = cloning(current_path, repo_path, project['name'])
                if r == 0:
                    cleaning(current_path, repo_path, projects)
                    sys.exit(-1)

        print "\nBuilding recipes:"
        for project in projects:
            name = project['name']
            recipe = project['recipe']
            try:
                revision = project['revision']
            except:
                revision = 'none'
            branches = project['branches']
            for branch in branches:
                branch_name = branch['branch']
                targets = branch['targets']
                if repo_path != 'none':
                    r = reseting(current_path, name, branch_name, revision)
                    if r == 0:
                        cleaning(current_path, repo_path, projects)
                        sys.exit(-1)
                for target in targets:
                    target_name = target['target']
                    run_qemu = target['qemu']
                    if recipe == 'c':
                        r = build_recipe_C(current_path, name, "%s_config"%target_name,
                                config, run_qemu, "  ", test_file)
                        if r == 0:
                            cleaning(current_path, repo_path, projects)
                            sys.exit(-1)
                    elif recipe == 'smart':
                        r = build_recipe_SM(current_path, name, "%s_config"%target_name,
                                config, run_qemu, "  ", test_file)
                        if r == 0:
                            cleaning(current_path, repo_path, projects)
                            sys.exit(-1)
                    else:
                        print "Unknown recipe '%s', skipping..."%recipe
        print "\n\n *** All recipes are successful ***\n"

        if end_cleaning == True:
            cleaning(current_path, repo_path, projects)

        if __name__ == "__main__":
            sys.exit(0)

    except Exception:
        print "Exception cleaning..."
        cleaning(current_path, repo_path, projects)

        type, value, history = sys.exc_info()
        traceback.print_exception(type, value, history, 10)
        sys.exit(-1)

def cleaning(current_path, repo_path, projects):
    if repo_path != 'none':
        for project in projects:
            name = project['name']
            subcommand("Deleting %s"%name, ['rm', '-rf', name], current_path, "  ")
            if name in services_users:
                subcommand("Deleting services", ['rm', '-rf', 'services'], current_path, "  ")

def cloning(current_path, repo_path, name):
    print "Project %s:"%name
    hgpath = os.path.join(repo_path, name)
    prjpath = os.path.join(current_path, name)
    r = subcommand("Cloning %s ..."%name, ['hg', 'clone', hgpath], current_path, "  ")
    if r != 0:
        r = subcommand("Updating %s ..."%name, ['hg', 'pull'], prjpath, "  ")

    if r != 0 and name in services_users:
        r = cloning(current_path, repo_path, 'services')

    return r

def reseting(current_path, name, branch_name, revision):
    prjpath = os.path.join(current_path, name)
    if revision != 'none':
        # Trying to sync on a given revision (e.g changeset)
        r = subcommand("Looking for rev: %s in %s ..."%(revision, name),
                ['hg', 'identify', '-r', revision], prjpath, "  ", err=False)
        if r == 1:
            r = subcommand("Reseting %s to revision %s ..."%(name, revision),
            ['hg', 'up', '-r', revision], prjpath, "  ")
            return r

    # Trying to sync on a given branch
    (r, brs) = subcommand("Looking for %s in %s branches..."%(branch_name, name),
        ['hg', 'branches'], prjpath, "  ", output=True)
    if r == 1:
        print " Found: \n", brs
        if branch_name in brs:
            branch = branch_name
        else:
            # Trying to sync default branch...
            branch = 'default'
        r = subcommand("Reseting %s to branch %s ..."%(name, branch),
                ['hg', 'up', branch], prjpath, "  ")

    if r != 0 and name in services_users:
        r = reseting(current_path, 'services', branch_name, revision)

    return r

if __name__ == "__main__":
    if len(sys.argv) > 2:
        main(sys.argv[1], sys.argv[2])
    elif len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main('config.json')
