#!/usr/bin/env python
import sys, os, json, time
from subprocess import Popen, PIPE

from code_sitter import main as RunConfig
from code_sitter_cmd import subcommand

c_recipe_users = ["kernelC"]
smart_recipe_users = ["kernelSM"]

def error_msg(msg):
    print "ERROR %s: %s" % (__file__,msg)

def main(repo, name, branch_name, target, rev="none", emu='qemu'):
    code_sitter_path = os.path.dirname(os.path.realpath(__file__))
    default_config_file = os.path.join(code_sitter_path, "config_buildbot.json")
    try:
        fp = open(default_config_file)
        jsconfig = json.load(fp)
        fp.close()
    except Exception as e:
        print "Unable to read configuration file '%s': %s\n"%(default_config_file, str(e))
        sys.exit(-1)

    if repo == "none":
        print "Unable to get repository informations..."
        sys.exit(-1)

    jsconfig['config']['repo-path'] = repo
    for project in jsconfig['projects']:
        project['name'] = name
        if name in c_recipe_users:
            project['recipe'] = 'c'
        elif name in smart_recipe_users:
            project['recipe'] = 'smart'
        else:
            error_msg("Invalid project name: [%s]." % name)
            sys.exit(-1)
        project['revision'] = rev
        for branch in project['branches']:
            branch['branch'] = branch_name
            for t in branch['targets']:
                t['target'] = target
                if emu == 'qemu':
                    t['qemu'] = 'true'
                else:
                    t['qemu'] = 'false'
                # Today, we only support a config with only one project containing
                # only one target...:
                break

    fp = open("config.json", 'w')
    json.dump(jsconfig, fp)
    fp.close()

    print "New generated config: ", jsconfig

    # Run code_sitter on this new config:
    RunConfig("config.json", end_cleaning=False)

    # Archive logs & files
    logname = "%s_%s_%s" % (target, name, branch_name)
    tool=os.path.join(code_sitter_path, "shell", "logs_store")
    r = subcommand("%s %s %s" % (tool,logname, os.getcwd()), [tool, logname, os.getcwd()], os.getcwd(), "  ", display=False)

if __name__ == "__main__":
    if len(sys.argv) > 6:
        main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
    elif len(sys.argv) > 5:
        main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    elif len(sys.argv) > 4:
        main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        error_msg(("Invalid num of args: ", sys.argv))
        sys.exit(-1)
