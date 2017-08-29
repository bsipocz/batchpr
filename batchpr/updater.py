import os
import abc
import six
import sys
import subprocess
from textwrap import indent

from termcolor import colored
import requests


GITHUB_RAW_FILENAME = "https://raw.githubusercontent.com/{repo}/master/{filename}"


class BranchExistsException(Exception):
    pass


@six.add_metaclass(abc.ABCMeta)
class Updater(object):

    def __init__(self, github):
        self.github = github
        self.user = github.get_user()
        self.repo = None
        self.fork = None

    def info(self, message):
        print(message)

    def run(self, repositories):

        if isinstance(repositories, six.string_types):
            repositories = [repositories]

        for repository in repositories:

            print(colored('Processing repository: {0}'.format(repository), 'cyan'))

            self.repo_name = repository

            try:
                print('  > Ensuring repository exists')
                self.ensure_repo_set_up()
            except Exception:
                self.error("    An error occurred when trying to get the repository")
                continue

            try:
                print('  > Ensuring fork exists (and creating if not)')
                self.ensure_fork_set_up()
            except Exception:
                self.error("    An error occurred when trying to set up a fork")
                continue

            try:
                self.clone_fork()
            except BranchExistsException:
                self.error("    Branch {0} already exists - skipping repository".format(self.branch_name))
                continue
            except Exception:
                self.error("    An error occurred - skipping repository")
                continue

            if not self.process_repo():
                self.warn("    Skipping repository")
                return

    def warn(self, message):
        print(colored(message, 'magenta'))

    def error(self, message):
        print(colored(message, 'red'))

    def check_file_exists(self, filename):
        r = requests.get(GITHUB_RAW_FILENAME.format(repo=self.repo_name, filename=filename))
        return r.status_code == 200

    def ensure_repo_set_up(self):
        self.repo = self.github.get_repo(self.repo_name)

    def ensure_fork_set_up(self):
        if self.repo.owner.login != self.user.login:
            self.fork = self.user.create_fork(self.repo)
        else:
            self.fork = self.repo

    def clone_fork(self, dirname='.'):

        # Go to working directory
        os.chdir(dirname)

        # Clone the repository
        self.run_command('git clone --depth 1 {0}'.format(self.fork.ssh_url))
        os.chdir(self.repo.name)

        # Make sure the branch doesn't already exist
        try:
            self.run_command('git checkout origin/{0}'.format(self.branch_name))
        except:
            pass
        else:
            raise BranchExistsException()

        # Update to the latest upstream master
        self.run_command('git remote add upstream {0}'.format(self.repo.clone_url))
        self.run_command('git fetch upstream')
        self.run_command('git checkout upstream/master')
        self.run_command('git checkout -b {0}'.format(self.branch_name))

        # Initialize submodules
        self.run_command('git submodule init')
        self.run_command('git submodule update')

    def open_pull_request(self):
        self.run_command('git commit -m "{0}"'.format(self.commit_message))
        self.run_command('git push origin {0}'.format(self.branch_name))
        self.repo.create_pull(title=self.commit_message,
                              body=self.pull_request_body,
                              base='master',
                              head='{0}:{1}'.format(self.fork.owner.login, self.branch_name))

    def run_command(self, command):
        print("  > {0}".format(command))
        p = subprocess.Popen(command, shell=True,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        p.wait()
        output = p.communicate()[0].decode('utf-8').strip()
        if ('--verbose' in sys.argv or p.returncode != 0) and output:
            print(indent(output, ' ' * 4))
        if p.returncode == 0:
            return output
        else:
            raise Exception("Command '{0}' failed".format(command))

    @abc.abstractmethod
    def process_repo(self):
        pass

    @abc.abstractproperty
    def branch_name(self):
        pass

    @abc.abstractproperty
    def commit_message(self):
        pass

    @abc.abstractproperty
    def pull_request_body(self):
        pass