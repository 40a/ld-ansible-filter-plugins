# (c) 2016, Allen Sanabria <asanabria@linuxdynasty.org>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from os import path, walk
import re

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):

    TRANSFERS_FILES = False

    def _set_args(self):
        """ Set instance variables based on the arguments that were passed
        """
        IGNORE_FILES = ['.*.md', '.*.py', '.*.pyc']
        VALID_ARGUMENTS = [
            'name', 'dir', 'depth', 'files_matching', 'ignore_files'
        ]
        for arg in self._task.args:
            if arg not in VALID_ARGUMENTS:
                return {
                    'failed': True,
                    'message': '{0} is not a valid option in debug'.format(arg)
                }
        self.return_results_as_name = self._task.args.get('name', None)
        self.source_dir = self._task.args.get('dir')
        self.depth = self._task.args.get('depth', 0)
        self.files_matching = self._task.args.get('files_matching', None)
        if self.files_matching:
            self.matcher = re.compile(r'{0}'.format(self.files_matching))
        else:
            self.matcher = None
        self.ignore_files = self._task.args.get('ignore_files', list())
        if isinstance(self.ignore_files, str):
            self.ignore_files = self.ignore_files.split()
        elif isinstance(self.ignore_files, dict):
            return {
                'failed': True,
                'message': '{0} must be a list'.format(self.ignore_files)
            }
        self.ignore_files.extend(IGNORE_FILES)

        if not self.source_dir:
            err_msg = '{0}{1}{2}{3}'.format(
                'No directory was found for the included vars. ',
                'Use `- include_vars_dir: <dirname>` or the `dir:` option ',
                'to specify the vars dirname.',
                self._task._ds
            )
            raise AnsibleError(err_msg)

    def run(self, tmp=None, task_vars=None):
        """ Load yml files recursively from a directory.
        """
        self.show_content = True
        self._set_args()
        if not task_vars:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        results = dict()
        if self._task._role:
            if self.source_dir == 'vars':
                self.source_dir = (
                    path.join(self._task._role._role_path, self.source_dir)
                )
            else:
                self.source_dir = (
                    path.join(
                        self._task._role._role_path, 'vars', self.source_dir
                    )
                )
        if path.exists(self.source_dir):
            for root_dir, filenames in self._traverse_dir_depth():
                failed, err_msg, updated_results = (
                    self._load_files(root_dir, filenames)
                )
                if not failed:
                    results.update(updated_results)
                else:
                    result['failed'] = failed
                    result['message'] = err_msg
                    break

            if self.return_results_as_name:
                scope = dict()
                scope[self.return_results_as_name] = results
                results = scope

            result['ansible_facts'] = results
            result['_ansible_no_log'] = self.show_content
        else:
            result['failed'] = True
            result['message'] = (
                '{0} directory does not exist'.format(self.source_dir)
            )

        return result

    def _traverse_dir_depth(self):
        """ Recursively iterate over a directory and sort the files in
            alphabetical order. Do not iterate pass the set depth.
            The default depth is unlimited.
        """
        current_depth = 0
        sorted_walk = list(walk(self.source_dir))
        sorted_walk.sort(key=lambda x: x[0])
        for current_root, current_dir, current_files in sorted_walk:
            current_depth += 1
            if current_depth <= self.depth or self.depth == 0:
                current_files.sort()
                yield (current_root, current_files)
            else:
                break

    def _ignore_file(self, filename):
        """ Return True if a file matches the list of ignore_files.
        Args:
            filename (str): The filename that is being matched against.

        Returns:
            Boolean
        """
        for file_type in self.ignore_files:
            try:
                if re.search(r'{0}$'.format(file_type), filename):
                    return True
            except Exception:
                err_msg = 'Invalid regular expression: {0}'.format(file_type)
                raise AnsibleError(err_msg)
        return False

    def _load_files(self, root_dir, var_files):
        """ Load the found yml files and update/overwrite the dictionary.
        Args:
            root_dir (str): The base directory of the list of files that is being passed.
            var_files: (list): List of files to iterate over and load into a dictionary.

        Returns:
            Tuple (bool, str, dict)
        """
        results = dict()
        failed = False
        err_msg = ''
        for filename in var_files:
            stop_iter = False
            # Never include main.yml from a role, as that is the default included by the role
            if self._task._role:
                if filename == 'main.yml':
                    stop_iter = True
                    continue

            filepath = path.join(root_dir, filename)
            if self.files_matching:
                if not self.matcher.search(filename):
                    stop_iter = True

            if not stop_iter and not failed:
                if path.exists(filepath) and not self._ignore_file(filename):
                    data, show_content = (
                        self._loader._get_file_contents(filepath)
                    )
                    data = self._loader.load(data, show_content)
                    if not show_content:
                        self.show_content = False
                    if data is None:
                        data = dict()
                    if not isinstance(data, dict):
                        failed = True
                        err_msg = (
                            '{0} must be stored as a dictionary/hash'
                            .format(filepath)
                        )
                    else:
                        results.update(data)
        return failed, err_msg, results
