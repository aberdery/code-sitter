#!/usr/bin/env python
import sys, os, threading, json, pexpect
from subprocess import Popen, PIPE

class Tests():
    def __init__(self, test_file, root, config, prefix=None):
        self.root      = root
        self.test_dir  = 'tests'
        self.test_name = 'test'
        self.log_file  = os.path.join(self.root, "..", 'default_tests_log.txt')
        try:
            services_path=config['services-path']
        except:
            services_path=os.path.join(self.root, "..", "services")
        print "##################### ABE DBG services: ", services_path
        self.lib_file  = os.path.join(services_path, "tests_domains", 'tests_lib.json')
        self.timeout   = 20
        self.prefix    = '  ' + prefix
        try:
            fp = open(test_file)
            self.tests = json.load(fp)
            fp.close()
        except Exception as e:
            print "Unable to read test suite file '%s': %s\n"%(test_file, str(e))
            sys.exit(-1)
        try:
            fp = open(self.lib_file)
            self.lib = json.load(fp)
            fp.close()
        except Exception as e:
            print "Unable to read tests lib file '%s': %s\n"%(self.lib_file, str(e))
            sys.exit(-1)

        self.session = {"tests":0, "pass":0, "fail":0, "inconclusive":0, "not_run":0}
        self.list    = []

    def run(self, emu_bin=None, emu_args=None):
        f=open(self.log_file, 'w')
        for test in self.list:
            self.session['tests']+=1
            tcmd = test['path']
            if test['args'] != 'none':
                tcmd += ' ' + test['args']
            t = self.timeout
            try:
                t = test['timeout']
            except:
                pass
            p = pexpect.spawn(emu_bin, emu_args, cwd=self.root, logfile=f)
            p.expect('ProvenCore\[', timeout=t)
            p.sendline(tcmd)
            idx = p.expect(['<--- PNC TEST STATUS:', 'Command failed', pexpect.TIMEOUT], timeout=t)
            if idx == 1:
                print "%sTest %s: NOT RUN" % (self.prefix, test['path'])
                self.session['not_run']+=1
            elif idx == 2:
                print "%sTest %s: TIMEOUT" % (self.prefix, test['path'])
                self.session['fail']+=1
            else:
                idx=p.expect(['PASS', 'FAIL', 'INCONCLUSIVE'])
                if idx == 0:
                    print "%sTest %s: PASS" % (self.prefix, test['path'])
                    self.session['pass']+=1
                elif idx == 1:
                    print "%sTest %s: FAIL" % (self.prefix, test['path'])
                    self.session['fail']+=1
                elif idx == 2:
                    print "%sTest %s: INCONCLUSIVE" % (self.prefix, test['path'])
                    self.session['inconclusive']+=1
        f.close()
        print "%sSUMMARY: %d tests, %d PASS, %d FAIL, %d INCONCLUSIVE, %d NOT RUN" % \
        (self.prefix, self.session['tests'], self.session['pass'], self.session['fail'], \
        self.session['inconclusive'], self.session['not_run'])

    def config(self):
        tmplist=[]

        # Update config.mk to build init with only shell
        afile = os.path.join(self.root, 'config.mk')
        fp = open(afile, 'a')
        fp.write('FEATURES += INIT_SHELL\n')
        fp.close()
        print "%s  config.mk updated successfully."%self.prefix

        # Build list of tests to run looking for matching id between test suite and
        # tests lib in order to find out test's path...
        for test in self.tests['tests']:
            found = 0
            path = None
            for domain in self.lib['domains']:
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
                print "%s  test: [%s] is not a valid/known test."%(self.prefix, test['id'])
                self.session['tests']+=1
                self.session['not_run']+=1
            else:
                test['path'] = os.path.join(self.test_dir, path, self.test_name)
                self.list.append(test)

        # Create pnc_tests.mk containing all test domains to build/link in image
        tfile = os.path.join(self.root, 'pnc_tests.mk')
        subcommand("rm -f %s"%tfile, ['rm', '-f', tfile], self.root, "%s  "%self.prefix, display=False)
        if len(tmplist) != 0:
            fp = open(tfile, 'w')
            fp.write('PNC_TESTS := \\\n')
            for path in tmplist:
                fp.write('  '+path+'\\\n')
            fp.close()
            print "%s  pnc_tests.mk created successfully."%self.prefix

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

def subcommand(cmd, cmdlist, path, prefix, display=True, output=False, err=True):
    '''
    Parameters description:
    cmd:     string describing command that will be executed.
    cmdlist: list that will contain entire cmd & parameters and that will be
             executed through subprocess.Popen
    path:    path where to execute command
    prefix:  prepend prefix to any display provided by subcommand.
             May be simply ''
    display: When True (default), command's end message is printed.
             Otherwise, command will be silent unless it goes in error...
             Can be used to False to avoid too much logging due to "non important"
             commands...
    output:  Default to False.
             When True, subcommand returns status AND full log of the command
    err:     Default to True: when subcommand goes in error, it displays error
             messages.
             When set to False, subcommand returns error status silently: this to
             avoid logging known faulty commands (ex: look for branch or revision
             in a Mercurial depot...).
    '''
    ret = 1
    proc = Popen(cmdlist, stdout=PIPE, cwd=path)
    cmd_output = ""
    while proc.poll() is None:
       cmd_output += proc.stdout.readline()
    cmd_output += proc.stdout.read()
    if proc.returncode != 0:
        if err == True:
            print "%sCommand failure: %s"%(prefix, cmd)
            print "%sFull log:\n%s\n"%(prefix, cmd_output)
            print "%sCommand '%s' failed with error code %d"%(prefix, cmd, proc.returncode)
        ret = 0
    else:
        if display == True:
            print "%sCommand completed successfully: %s"%(prefix, cmd)

    if output == True:
        return ret, cmd_output
    else:
        return ret


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

def build_recipe(path, name, target, config, run_qemu, prefix, test_file):
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
    r = subcommand("make mrproper", ['make', 'mrproper'], full_path, "%s  "%prefix)
    if r == 0:
        return r
    r = subcommand("make distclean", ['make', 'distclean'], full_path, "%s  "%prefix)
    if r == 0:
        return r
    r = subcommand("make %s %s"%(target, cross_compile), ['make', target, cross_compile], full_path, "%s  "%prefix)
    if r == 0:
        return r
    if test_file != None:
        tests = Tests(test_file, full_path, config, prefix)
        tests.config()
    r = subcommand("make config %s"%cross_compile, ['make', 'config', cross_compile], full_path, "%s  "%prefix)
    if r == 0:
        return r
    r = subcommand("make programs %s"%cross_compile, ['make', 'programs', cross_compile], full_path, "%s  "%prefix)
    if r == 0:
        return r
    r = subcommand("make %s"%cross_compile, ['make', 'all', cross_compile], full_path, "%s  "%prefix)
    if r == 0:
        return r
    print "%sBuilding %s:%s is a success.\n"%(prefix, name,target)

    # run qemu with/without tests
    if run_qemu == 'true' or run_qemu == True:
        try:
            qemu_path = config['qemu-path']
            qemu_bin = os.path.join(qemu_path, config['qemu-bin'])
            qemu_cmd = [qemu_bin] + config['qemu-args'].split(' ')
        except Exception as e:
            print "Configuration issue: can't create qemu command: %s"%str(e)
            return 0
        if test_file == None:
            RunCmd(qemu_cmd, PIPE, full_path, 5).Run()
        else:
            print "%sRunning tests for %s:%s"%(prefix, name,target)
            tests.run(emu_bin=qemu_bin, emu_args=config['qemu-args'].split(' '))
    return 1

def setup_recipe(path, name, prefix):
    full_path = os.path.join(path, name)
    print "%sPreparing %s/IMP."%(prefix, name)
    r = subcommand("sh setup_kernel.sh", ['sh', 'setup_kernel.sh'], full_path, "%s  "%prefix)
    return r

def build_recipe_C(path, name, target, config, run_qemu, prefix, test_file=None):
    return build_recipe(path, name, target, config, run_qemu, prefix, test_file)

def build_recipe_SM(path, name, target, config, run_qemu, prefix, test_file=None):
    r = setup_recipe(path, name, prefix)
    if r == 0:
        return r
    return build_recipe(os.path.join(path, name), "IMP", target, config, run_qemu, prefix, test_file)
