# -*- coding: utf-8 -*-
#
# Copyright (c) 2015, Alcatel-Lucent Inc
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the copyright holder nor the names of its contributors
#       may be used to endorse or promote products derived from this software without
#       specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import logging
import importlib
import re
import pkg_resources

from bambou.exceptions import BambouHTTPError
from printer import Printer


class Utils(object):
    """ Utils """

    INVARIANT_RESOURCES = ['qos', 'vrs', 'cms']

    @classmethod
    def _clean_name(cls, string):
        """ String cleaning for specific cases

            This is very specific and is used to force
            some underscore while using get_python_name.

            Args:
                string: the string to clean

            Returns:
                Returns a clean string
        """
        rep = {
            "VPort": "Vport",
            "IPID": "IpID"
        }

        rep = dict((re.escape(k), v) for k, v in rep.iteritems())
        pattern = re.compile("|".join(rep.keys()))
        return pattern.sub(lambda m: rep[re.escape(m.group(0))], string)

    @classmethod
    def get_python_name(cls, name):
        """ Transform a given name to python name """
        first_cap_re = re.compile('(.)([A-Z](?!s([A-Z])*)[a-z]+)')
        all_cap_re = re.compile('([a-z0-9])([A-Z])')

        s1 = first_cap_re.sub(r'\1_\2', Utils._clean_name(name))
        return all_cap_re.sub(r'\1_\2', s1).lower()

    @classmethod
    def get_singular_name(cls, plural_name):
        """ Returns the singular name of the plural name """

        if plural_name in Utils.INVARIANT_RESOURCES:
            return plural_name

        if plural_name[-3:] == 'ies':
            return plural_name[:-3] + 'y'

        if plural_name[-1] == 's':
            return plural_name[:-1]

        return plural_name

    @classmethod
    def get_plural_name(cls, singular_name):
        """ Returns the plural name of the singular name """

        if singular_name in Utils.INVARIANT_RESOURCES:
            return singular_name

        vowels = ['a', 'e', 'i', 'o', 'u', 'y']
        if singular_name[-1:] == 'y' and singular_name[-2] not in vowels:
            return singular_name[:-1] + 'ies'

        if singular_name[-1:] == 's':
            return singular_name

        return singular_name + 's'

    @classmethod
    def get_vspk_version(cls, version):
        """ Get the vspk version according to the given version

            Args:
                version (int): the version

            Returns:
                version as string

            Example:
                get_vspk_version(3.1)
                >>> v3_1

        """
        return ('v%s' % version).replace('.', '_')


class VSDKInspector(object):
    """ Utils to access VSDK objects

    """

    def __init__(self, version=None):
        """ Initializes

        """
        if version:
            self._version = Utils.get_vspk_version(version)

        self._objects_mapping = {}
        self._ignored_resources = ['me']
        self._vsdk = None

        self._load_objects()

    def _load_objects(self):
        """ Load objects in a temporary database

        """
        self._get_vsdk_package()

        object_names = [name for name in dir(self._vsdk) if name != 'NUVSDSession' and name.startswith('NU') and not name.endswith('Fetcher') and name != 'NURESTModelController']

        for object_name in object_names:
            obj = getattr(self._vsdk, object_name)
            self._objects_mapping[obj.rest_name] = object_name

    def _get_vsdk_package(self):
        """ Returns vsdk package

        """
        if self._vsdk is None:
            try:
                self._vsdk = importlib.import_module('vspk.vsdk.%s' % self._version)
                # Printer.info('Imported vsdk.%s from VSPK.' % self._version)
            except ImportError:
                try:
                    self._vsdk = importlib.import_module('vsdk')
                except ImportError as error:
                    Printer.raise_error('Please install requirements using command line `pip install -r requirements.txt`.\n%s' % error)

        return self._vsdk

    def get_all_objects(self):
        """ Returns all objects from the VSD

        """
        resources = self._objects_mapping.keys()
        resources = [Utils.get_plural_name(name) for name in resources if name not in self._ignored_resources]

        return resources

    def get_vsdk_class(self, name):
        """ Get a VSDK class object

            Args:
                name: the name of the object

            Returns:
                a VSDK class object

        """
        if name in self._objects_mapping:
            classname = self._objects_mapping[name]

            klass = None
            try:
                klass = getattr(self._vsdk, classname)
            except:
                Printer.raise_error('Unknown class %s' % classname)

            return klass

        Printer.raise_error('Unknown object named %s' % name)

    def get_vsdk_instance(self, name):
        """ Get VSDK object instance according to a given name

            Args:
                name: the name of the object

            Returns:
                A VSDK object or raise an exception
        """
        klass = self.get_vsdk_class(name)
        return klass()

    def get_vsdk_parent(self, parent_infos, user):
        """ Get VSDK parent object if possible
            Otherwise it will take the user

            Args:
                parent_infos: a list composed of (parent_name, uuid)

            Returns:
                A parent if possible otherwise the user in session

        """
        if parent_infos and len(parent_infos) == 2:
            name = parent_infos[0]
            uuid = parent_infos[1]

            singular_name = Utils.get_singular_name(name)
            parent = self.get_vsdk_instance(singular_name)
            parent.id = uuid

            try:
                (parent, connection) = parent.fetch()
            except Exception, ex:
                Printer.raise_error('Failed fetching parent %s with uuid %s\n%s' % (name, uuid, ex))

            return parent

        return user

    def get_user_session(self, args):
        """ Get api key

            Args:
                username: username to get an api key
                password: password to get an api key
                api: URL of the API endpoint
                enterprise: Name of the enterprise to connect

            Returns:
                Returns an API Key if everything works fine
        """
        self._set_verbose_mode(args.verbose)
        session = self._vsdk.NUVSDSession(username=args.username, password=args.password, enterprise=args.enterprise, api_url=args.api)
        try:
            session.start()
        except BambouHTTPError as error:
            status_code = error.connection.response.status_code
            if status_code == 401:
                Printer.raise_error('Could not log in to the VSD %s (API %s) with username=%s password=%s enterprise=%s' % (args.api, args.version, args.username, args.password, args.enterprise))
            else:
                Printer.raise_error('Cannot access VSD %s [HTTP %s]. Current vsdk version tried to connect to the VSD API %s' % (args.api, status_code, args.version))

        user = session.user

        if user.api_key is None:
            Printer.raise_error('Could not get a valid API key. Activate verbose mode for more information')

        return session

    def _set_verbose_mode(self, verbose):
        """ Defines verbosity

            Args:
                verbose: Boolean to activate or deactivate DEBUG mode

        """
        if verbose:
            Printer.info('Verbose mode is now activated.')
            self._vsdk.set_log_level(logging.DEBUG)
        else:
            self._vsdk.set_log_level(logging.ERROR)
