# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import glob
import os.path
from stevedore import extension

from oslo.config import cfg

from senlin.common import exception
from senlin.common.i18n import _
from senlin.common.i18n import _LE
from senlin.common.i18n import _LI
from senlin.engine import clients
from senlin.engine import parser
from senlin.engine import registry
from senlin.openstack.common import log


LOG = log.getLogger(__name__)

_environment = None


def global_env():
    if _environment is None:
        initialize()
    return _environment


class Environment(object):
    '''
    An object that contains all profiles, policies and customizations.
    '''
    SECTIONS = (
        PARAMETERS, CUSTOM_PROFILES, CUSTOM_POLICIES,
    ) = (
        'parameters', 'custom_profiles', 'custom_policies',
    )

    def __init__(self, env=None, is_global=False):
        '''
        Create an Environment from a dict.

        :param env: the json environment
        :param is_global: boolean indicating if this is a user created one.
        '''
        self.params = {}
        self.profile_registry = registry.Registry('profiles', is_global)
        self.policy_registry = registry.Registry('policies', is_global)

        if env is None:
            env = {}
        else:
            # Merge user specified keys with current environment 
            self.params = env.get(self.PARAMETERS, {})
            custom_profiles = env.get(self.CUSTOM_PROFILES, {})
            custom_policies = env.get(self.CUSTOM_POLICIES, {})
            self.profile_registry.load(custom_profiles)
            self.policy_registry.load(custom_policies)

    def parse(self, env_str):
        '''
        Parse a string format environment file into a dictionary.
        '''
        if env_str is None:
            return {}

        env = parser.simple_parse(env_str)

        # Check unknown sections
        for sect in env:
            if sect not in self.SECTIONS:
                msg = _('environment has unknown section "%s"') % sect
                raise ValueError(msg)

        # Fill in default values for missing sections
        for sect in self.SECTIONS:
            if sect not in env:
                env[sect] = {}

        return env

    def load(self, env_dict):
        '''
        Load environment from the given dictionary.
        '''
        self.params.update(env_dict.get(self.PARAMETERS, {}))
        self.profile_registry.load(env_dict.get(self.CUSTOM_PROFILES, {}))
        self.policy_registry.load(env_dict.get(self.CUSTOM_POLICIES, {}))

    def _check_profile_type_name(self, name):
        if name == "" or name is None:
            msg = _('Profile type name not specified')
            raise exception.ProfileValidationFailed(message=msg)
        elif not isinstance(name, six.string_types):
            msg = _('Profile type name is not a string')
            raise exception.ProfileValidationFailed(message=msg)

    def register_profile(self, name, plugin):
        self._check_profile_type_name(name)
        self.profile_registry.register_plugin(name, plugin)

    def get_profile(self, name):
        self._check_profile_type_name(name)
        plugin = self.profile_registry.get_plugin(name)
        if plugin is None:
            msg = _("Unknown profile type : %s") % name
            raise exception.ProfileValidationFailed(message=msg)
        return plugin

    def get_profile_types(self):
        return self.profile_registry.get_types()

    def _check_policy_type_name(self, name):
        if name == "" or name is None:
            msg = _('Policy type name not specified')
            raise exception.PolicyValidationFailed(message=msg)
        elif not isinstance(name, six.string_types):
            msg = _('Policy type name is not a string')
            raise exception.PolicyValidationFailed(message=msg)

    def register_policy(self, name, plugin):
        self._check_policy_type_name(name)
        self.policy_registry.register_plugin(name, plugin)

    def get_policy(self, name):
        self._check_policy_type_name(name)
        plugin = self.policy_registry.get_plugin(name)
        if plugin is None:
            msg = _("Unknown policy type : %s") % name
            raise exception.PolicyValidationFailed(message=msg)
        return plugin

    def get_policy_types(self):
        return self.policy_registry.get_types()

    def read_global_environment(self):
        '''
        Read and parse global enviroment files.
        '''
        cfg.CONF.import_opt('environment_dir', 'senlin.common.config')
        env_dir = cfg.CONF.environment_dir

        try:
            files = glob.glob(os.path.join(env_dir, '*'))
        except OSError as ex:
            LOG.error(_LE('Failed to read %s'), env_dir)
            LOG.exception(ex)
            return

        for fname in files:
            try:
                with open(fname) as f:
                    LOG.info(_LI('Loading environment from %s'), fname)
                    self.load(self.parse(f.read()))
            except ValueError as vex:
                LOG.error(_LE('Failed to parse %s'), fname)
                LOG.exception(vex)
            except IOError as ioex:
                LOG.error(_LE('Failed to read %s'), fname)
                LOG.exception(ioex)


def initialize():

    global _environment

    def _get_mapping(namespace):
        mgr = extension.ExtensionManager(
            namespace=namespace,
            invoke_on_load=False,
            verify_requirements=True)
        return [[name, mgr[name].plugin] for name in mgr.names()]

    if _environment is not None:
        return

    # TODO(Qiming): Check when to initialize clients if needed
    clients.initialise()

    env = Environment(is_global=True)

    # Register global plugins when initialized
    entries = _get_mapping('senlin.profiles')
    for name, plugin in entries:
        env.register_profile(name, plugin)

    entries = _get_mapping('senlin.policies')
    for name, plugin in entries:
        env.register_policy(name, plugin)

    env.read_global_environment()
    _environment = env