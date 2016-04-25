#!/usr/bin/env python
import sys, os, json, traceback
from datetime import datetime
from subprocess import Popen, PIPE

from code_sitter_cmd import build_recipe_C, build_recipe_SM, subcommand

def main(config_file, test_file=None):
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
        try:
            default_branch = config['default-branch']
        except Exception:
            default_branch = "default"

        now = datetime.now()
        print "\n *** Compilation Test: %s ***\n"%(str(now))

        if repo_path != 'none':
            cleaning(current_path, repo_path, projects)

            print "\nCloning projects:"
            for project in projects:
                name = project['name']
                hgpath = os.path.join(repo_path, name)
                prjpath = os.path.join(current_path, name)
                print "Project %s:"%name
                r = subcommand("Cloning %s ..."%name, ['hg', 'clone', hgpath], current_path, "  ")
                if r == 0:
                    cleaning(current_path, repo_path, projects)
                    sys.exit(-1)
                r = subcommand("Updating %s ..."%name, ['hg', 'pull'], prjpath, "  ")
                if r == 0:
                    cleaning(current_path, repo_path, projects)
                    sys.exit(-1)

        print "\nBuilding recipes:"
        for project in projects:
            name = project['name']
            recipe = project['recipe']
            try:
                fallback_branch = project['default-branch']
            except Exception:
                fallback_branch = default_branch
            if recipe == 'none':
                print "Skipping project '%s'. Reseting to branch %s"%(name,fallback_branch)
                continue
            branches = project['branches']
            for branch in branches:
                branch_name = branch['branch']
                targets = branch['targets']
                if repo_path != 'none':
                    r = subcommand("Reseting %s to branch %s ..."%(name, branch_name),
                            ['hg', 'up', branch_name], prjpath, "  ")
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

        cleaning(current_path, repo_path, projects)
        sys.exit(0)
    except Exception:
        if repo_path != 'none':
            print "Exception cleaning:"
            for project in projects:
                name = project['name']
                subcommand("Deleting %s"%name, ['rm', '-rf', name], current_path, "  ")

        type, value, history = sys.exc_info()
        traceback.print_exception(type, value, history, 10)
        sys.exit(-1)

def cleaning(current_path, repo_path, projects):
    if repo_path != 'none':
        for project in projects:
            name = project['name']
            subcommand("Deleting %s"%name, ['rm', '-rf', name], current_path, "  ")

if __name__ == "__main__":
    if len(sys.argv) > 2:
        main(sys.argv[1], sys.argv[2])
    elif len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main('config.json')
