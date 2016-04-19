#!/usr/bin/env python
import sys, os, threading, json, pexpect
from subprocess import Popen, PIPE

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
    prefix = '  ' + prefix
    num_tests=0
    num_pass=0
    num_fail=0
    num_inc=0
    num_notrun=0
    #default timeout: 20s
    timeout = 20

    f=open(os.path.join('default_tests_log.txt'), 'w')
    for domain in tests['domains']:
        for test in domain['tests']:
            num_tests+=1
            tcmd = test['name']
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
                print "%sTest %s: NOT RUN" % (prefix, test['name'])
                num_notrun+=1
            elif idx == 2:
                print "%sTest %s: TIMEOUT" % (prefix, test['name'])
                num_fail+=1
            else:
                idx=p.expect(['PASS', 'FAIL', 'INCONCLUSIVE'])
                if idx == 0:
                    print "%sTest %s: PASS" % (prefix, test['name'])
                    num_pass+=1
                elif idx == 1:
                    print "%sTest %s: FAIL" % (prefix, test['name'])
                    num_fail+=1
                elif idx == 2:
                    print "%sTest %s: INCONCLUSIVE" % (prefix, test['name'])
                    num_inc+=1

    f.close()
    return num_tests, num_pass, num_fail, num_inc, num_notrun

def configTests(tests, path, prefix=None):
    # Update config.mk to build init with only shell
    afile = os.path.join(path, 'config.mk')
    f = open(afile, 'a')
    f.write('FEATURES += INIT_SHELL\n')
    f.close()
    print "%s  config.mk updated successfully."%prefix

    # Create pnc_tests.mk containing all test domains to build/link in image
    tfile = os.path.join(path, 'pnc_tests.mk')
    subcommand("rm -f %s"%tfile, ['rm', '-f', tfile], path, "%s  "%prefix, display=False)
    f = open(tfile, 'w')
    f.write('PNC_TESTS := \\\n')
    for domain in tests['domains']:
        f.write('  '+domain['name']+'\\\n')
    f.close()
    print "%s  pnc_tests.mk created successfully."%prefix

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
        configTests(tests, full_path, prefix)
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
            (n, p, f, i, nr)=runTests(tests, full_path, prefix, emu_bin=qemu_bin, emu_args=config['qemu-args'].split(' '))
            print "%sSUMMARY: %d tests, %d PASS, %d FAIL, %d INCONCLUSIVE, %d NOT RUN" % (prefix, n, p, f, i, nr)

def setup_recipe(path, name, prefix):
    full_path = os.path.join(path, name)
    print "%sPreparing %s/IMP."%(prefix, name)
    subcommand("sh setup_kernel.sh", ['sh', 'setup_kernel.sh'], full_path, "%s  "%prefix)

def build_recipe_C(path, name, target, config, run_qemu, prefix, tests=None):
    build_recipe(path, name, target, config, run_qemu, prefix, tests)

def build_recipe_SM(path, name, target, config, run_qemu, prefix, tests=None):
    setup_recipe(path, name, prefix)
    build_recipe(os.path.join(path, name), "IMP", target, config, run_qemu, prefix, tests)
