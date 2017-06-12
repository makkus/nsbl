#!/usr/bin/python

from requests.structures import CaseInsensitiveDict

import pprint
import os
import yaml
import frkl

try:
    set
except NameError:
    from sets import Set as set


from nsbl.nsbl import ensure_git_repo_format

FRECKLE_METADATA_FILENAME = ".freckle"
NO_INSTALL_MARKER_FILENAME = ".no_install.freckle"
NO_STOW_MARKER_FILENAME = ".no-stow.freckle"

PACKAGES_METADATA_FILENAME = ".packages.freckle"

class FilterModule(object):
    def filters(self):
        return {
            'ensure_list_filter': self.ensure_list_filter,
            'dotfile_repo_filter': self.dotfile_repo_filter,
            'git_repo_filter': self.git_repo_filter,
            'pkg_mgr_filter': self.pkg_mgr_filter,
            'additional_packages_filter': self.additional_packages_filter
        }


    def pkg_mgr_filter(self, dotfile_repos, prefix=None):

        packages = self.dotfile_repo_filter(dotfile_repos)
        pkg_mgrs = set()

        for p in packages:
            pkg_mgr = p["vars"].get("pkg_mgr", None)
            if pkg_mgr:
                if prefix:
                    pkg_mgr = "{}{}".format(prefix, pkg_mgr)
                pkg_mgrs.add(pkg_mgr)

        return list(pkg_mgrs)


    def ensure_list_filter(self, dotfile_repos):

        if isinstance(dotfile_repos, dict):
            return [dotfile_repos]
        elif isinstance(dotfile_repos, (list, tuple)):
            return dotfile_repos

    def git_repo_filter(self, dotfile_repos):

        if isinstance(dotfile_repos, dict):
            dotfile_repos = [dotfile_repos]
        elif not isinstance(dotfile_repos, (list, tuple)):
            raise Exception("Not a valid type for dotfile_repo, can only be dict or list of dicts")

        result = []
        for dr in dotfile_repos:
            temp = ensure_git_repo_format(dr)
            result.append(temp)

        return result

    def additional_packages_filter(self, dotfile_repos):

        if isinstance(dotfile_repos, dict):
            dotfile_repos = [dotfile_repos]
        elif not isinstance(dotfile_repos, (list, tuple)):
            raise Exception("Not a valid type for dotfile_repo, can only be dict or list of dicts")

        pkgs = []
        for dr in dotfile_repos:
            temp = ensure_git_repo_format(dr)
            dest = temp["dest"]
            packages_metadata = os.path.expanduser(os.path.join(dest, PACKAGES_METADATA_FILENAME))
            if os.path.exists(packages_metadata):
                pkgs.append(packages_metadata)

        format = {"child_marker": "packages",
                  "default_leaf": "vars",
                  "default_leaf_key": "name",
                  "key_move_map": {'*': "vars"}}
        chain = [frkl.EnsureUrlProcessor(), frkl.EnsurePythonObjectProcessor(), frkl.FrklProcessor(format)]

        frkl_obj = frkl.Frkl(pkgs, chain)

        packages = frkl_obj.process()

        return packages



    def dotfile_repo_filter(self, dotfile_repos):

        if isinstance(dotfile_repos, dict):
            dotfile_repos = [dotfile_repos]
        elif not isinstance(dotfile_repos, (list, tuple)):
            raise Exception("Not a valid type for dotfile_repo, can only be dict or list of dicts")

        return self.create_dotfiles_dict(dotfile_repos)



    def create_dotfiles_dict(self, dotfile_repos):
        """Walks through all the provided dotfiles, and creates a dictionary with values according to what it finds, per folder.

        Args:
           dotfile_repos (list): a list of dotfile dictionaries (see: XXX)
        """

        apps = []

        for dir in dotfile_repos:
            dest = dir.get("dest", False)
            repo = dir.get("repo", "")
            paths = dir.get("paths", [])

            if not dest:
                if not repo:
                    raise Exception("Neither 'dest' nor 'repo' provided for freckles directory: ".format(dotfile_repos))

                temp = ensure_git_repo_format(repo)
                dest = temp['dest']


            if not paths:
                paths = [""]

            for dotfile_path in paths:

                temp_full_path = os.path.expanduser(os.path.join(dest, dotfile_path))

                if not os.path.isdir(temp_full_path):
                    # ignoring, not a directory
                    continue

                for item in os.listdir(temp_full_path):
                    if not item.startswith(".") and os.path.isdir(os.path.join(temp_full_path, item)):
                        # defaults
                        dotfile_dir = os.path.join(temp_full_path, item)
                        app = {}
                        app['folder_name'] = item
                        app['dotfile_dotfile_dir'] = dotfile_dir
                        app['dotfile_parent_path'] = temp_full_path
                        app['dotfile_dest'] = dest
                        if repo:
                            app['dotfile_repo'] = repo
                        if dotfile_path:
                            app['dotfile_relative_path'] = dotfile_path

                        freckles_metadata_file = os.path.join(dotfile_dir, FRECKLE_METADATA_FILENAME)
                        if os.path.exists(freckles_metadata_file):
                            stream = open(freckles_metadata_file, 'r')
                            temp = yaml.load(stream)
                            app.update(temp)

                        no_install_file = os.path.join(dotfile_dir, NO_INSTALL_MARKER_FILENAME)
                        if os.path.exists(no_install_file):
                            app['no_install'] = True

                        no_stow_file = os.path.join(dotfile_dir, NO_STOW_MARKER_FILENAME)
                        if os.path.exists(no_stow_file):
                            app['no_stow'] = True

                        # if "name" not in app.keys():
                            # if app.get("pkg_mgr", None) == "git" and "repo" in app.keys():
                                # app["name"] = app["repo"]
                            # else:
                                # app["name"] = item
                        package_dict = {"packages": {item: app}}
                        apps.append(package_dict)

        format = {"child_marker": "packages",
              "default_leaf": "vars",
              "default_leaf_key": "name",
              "key_move_map": {'*': "vars"}}
        chain = [frkl.FrklProcessor(format)]

        frkl_obj = frkl.Frkl(apps, chain)
        temp = frkl_obj.process()

        return temp
