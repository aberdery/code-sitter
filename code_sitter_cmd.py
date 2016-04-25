#!/usr/bin/env python
import sys, os, threading, json, pexpect
from subprocess import Popen, PIPE

TEST_SESSION={
    "tests":0,
    "pass":0,
    "fail":0,
    "inconclusive":0,
    "not_run":0 }

class RunCmd(threading.Thread):
    def __init__(self, cmd, outpipe, cwd, timeout):
        threading.Thread.__init__(self)
        self.cmd = cmd
        self.stdout = outpipe
        self.cwd = cwd
        self.timeout = timeout

    def run(self):
        self.p = Popen(self.cmd, stdout=self.stdout, cwd=self.cwd)
        self.p.wait()

    def Run(self):
        self.start()
        self.join(self.timeout)

        if self.is_alive():
            self.p.terminate()      #use self.p.kill() if process needs a kill -9
            print "RunCmd output:\n%s\n"%self.p.stdout.read()
            self.join()

def which(file):
    for path in os.environ["PATH"].split(os.pathsep):
        if os.path.exists(os.path.join(path, file)):
            return os.path.join(path, file)
    return None

def subcommand(cmd, cmdlist, path, prefix, display=True):
    proc = Popen(cmdlist, stdout=PIPE, cwd=path)
    cmd_output = ""
    while proc.poll() is None:
       cmd_output += proc.stdout.readline()
    cmd_output += proc.stdout.read()
    if proc.returncode != 0:
        print "%sCommand failure: %s"%(prefix, cmd)
        print "%sFull log:\n%s\n"%(prefix, cmd_output)
        print "%sCommand '%s' failed with error code %d"%(prefix, cmd, proc.returncode)
        sys.exit(-1)
    if display == True:
        print "%sCommand completed successfully: %s"%(prefix, cmd)

def runTests(tests, path, prefix, emu_bin=None, emu_args=None):
    # Run all tests one by one
    # For each test get end infos
    # Compute results
    global TEST_SESSION
    prefix = '  ' + prefix
    #default timeout: 20s
    timeout = 20

    f=open(os.path.join('default_tests_log.txt'), 'w')
    for test in tests:
        TEST_SESSION['tests']+=1
        tcmd = test['path']
        if test['args'] != 'none':
            tcmd += ' ' + test['args']
        t = timeout
        try:
            t = test['timeout']
        except:
            pass
        p = pexpect.spawn(emu_bin, emu_args, cwd=path, logfile=f)
        p.expect('ProvenCore\[', timeout=t)
        p.sendline(tcmd)
        idx = p.expect(['<--- PNC TEST STATUS:', 'Command failed', pexpect.TIMEOUT], timeout=t)
        if idx == 1:
            print "%sTest %s: NOT RUN" % (prefix, test['path'])
            TEST_SESSION['not_run']+=1
        elif idx == 2:
            print "%sTest %s: TIMEOUT" % (prefix, test['path'])
            TEST_SESSION['fail']+=1
        else:
            idx=p.expect(['PASS', 'FAIL', 'INCONCLUSIVE'])
            if idx == 0:
                print "%sTest %s: PASS" % (prefix, test['path'])
                TEST_SESSION['pass']+=1
            elif idx == 1:
                print "%sTest %s: FAIL" % (prefix, test['path'])
                TEST_SESSION['fail']+=1
            elif idx == 2:
                print "%sTest %s: INCONCLUSIVE" % (prefix, test['path'])
                TEST_SESSION['inconclusive']+=1
    f.close()
    return TEST_SESSION

def lookUpTestPath(id, tests_lib):
    # TODO: clever parsing of tests lib in python ??
    path = None
    for domain in tests_lib['domains']:
        if domain['id'] == id[0]:
            for case in domain['cases']:
                if id == case['id']:
                    path = case['dir']
    return path

def configTests(tests, root, prefix=None):
    global TEST_SESSION

    # Update config.mk to build init with only shell
    afile = os.path.join(root, 'config.mk')
    fp = open(afile, 'a')
    fp.write('FEATURES += INIT_SHELL\n')
    fp.close()
    print "%s  config.mk updated successfully."%prefix

    # Retreive tests library
    tests_lib_file = os.path.join(root, 'tests', 'tests_lib.json')
    try:
        fp = open(tests_lib_file)
        tests_lib = json.load(fp)
        fp.close()
    except Exception as e:
        print "Unable to read tests lib file '%s': %s\n"%(tests_lib_file, str(e))
        sys.exit(-1)

    # Build list of tests to run looking for matching id between test suite and
    # tests lib in order to find out test's path...
    tmplist=[]
    tests_list=[]
    for test in tests['tests']:
        found = 0
        path = None
        for domain in tests_lib['domains']:
            if domain['id'] == test['id'][0]:
                for case in domain['cases']:
                    if test['id'] == case['id']:
                        found = 1
                        path = case['dir']
                        if path not in tmplist:
                            tmplist.append(case['dir'])
                        break
            if found == 1:
                break
        if found == 0:
            print "%s  test: [%s] is not a valid/known test."%(prefix, test['id'])
            TEST_SESSION['tests']+=1
            TEST_SESSION['not_run']+=1
        else:
            test['path'] = os.path.join('tests', path, 'test')
            tests_list.append(test)

    # Create pnc_tests.mk containing all test domains to build/link in image
    tfile = os.path.join(root, 'pnc_tests.mk')
    subcommand("rm -f %s"%tfile, ['rm', '-f', tfile], root, "%s  "%prefix, display=False)
    if len(tmplist) != 0:
        f = open(tfile, 'w')
        f.write('PNC_TESTS := \\\n')
        for path in tmplist:
            f.write('  '+path+'\\\n')
        f.close()
        print "%s  pnc_tests.mk created successfully."%prefix

    return tests_list

def setup_toolchain(prefix):
    # check for <prefix>-gcc as direct path or in os.environ["PATH"]
    gcc = prefix + 'gcc'
    if not os.path.exists(gcc):
        path = which(gcc)
        if not path:
            toolchain = None
        else:
            toolchain = os.path.join(os.path.dirname(path), prefix)
    else:
        toolchain = prefix
    return toolchain

def build_recipe(path, name, target, config, run_qemu, prefix, tests=None):
    # Check if cross compile var is available
    try:
        cross_compile = "CROSS_COMPILE="
        toolchain = setup_toolchain(config['toolchain'])
        if toolchain != None:
            cross_compile = "CROSS_COMPILE=%s"%toolchain
    except Exception as e:
        pass

    print "%sBuilding %s:%s:"%(prefix, name,target)
    full_path = os.path.join(path, name)
    subcommand("make mrproper", ['make', 'mrproper'], full_path, "%s  "%prefix)
    subcommand("make distclean", ['make', 'distclean'], full_path, "%s  "%prefix)
    subcommand("make %s %s"%(target, cross_compile), ['make', target, cross_compile], full_path, "%s  "%prefix)
    if tests != None:
        tests_list = configTests(tests, full_path, prefix)
    subcommand("make config %s"%cross_compile, ['make', 'config', cross_compile], full_path, "%s  "%prefix)
    subcommand("make programs %s"%cross_compile, ['make', 'programs', cross_compile], full_path, "%s  "%prefix)
    subcommand("make %s"%cross_compile, ['make', 'all', cross_compile], full_path, "%s  "%prefix)
    print "%sBuilding %s:%s is a success.\n"%(prefix, name,target)

    # run qemu with/without tests
    if run_qemu:
        try:
            qemu_path = config['qemu-path']
            qemu_bin = os.path.join(qemu_path, config['qemu-bin'])
            qemu_cmd = [qemu_bin] + config['qemu-args'].split(' ')
        except Exception as e:
            print "Configuration issue: can't create qemu command: %s"%str(e)
            sys.exit(-1)
        if tests == None:
            RunCmd(qemu_cmd, PIPE, full_path, 5).Run()
        else:
            print "%sRunning tests for %s:%s"%(prefix, name,target)
            session=runTests(tests_list, full_path, prefix, emu_bin=qemu_bin, emu_args=config['qemu-args'].split(' '))
            print "%sSUMMARY: %d tests, %d PASS, %d FAIL, %d INCONCLUSIVE, %d NOT RUN" % \
            (prefix, session['tests'], session['pass'], session['fail'], session['inconclusive'], session['not_run'])

def setup_recipe(path, name, prefix):
    full_path = os.path.join(path, name)
    print "%sPreparing %s/IMP."%(prefix, name)
    subcommand("sh setup_kernel.sh", ['sh', 'setup_kernel.sh'], full_path, "%s  "%prefix)

def build_recipe_C(path, name, target, config, run_qemu, prefix, tests=None):
    build_recipe(path, name, target, config, run_qemu, prefix, tests)

def build_recipe_SM(path, name, target, config, run_qemu, prefix, tests=None):
    setup_recipe(path, name, prefix)
    build_recipe(os.path.join(path, name), "IMP", target, config, run_qemu, prefix, tests)
