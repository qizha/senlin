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

import six

from oslo_log import log as logging

from senlin.common import context
from senlin.common import exception
from senlin.common.i18n import _
from senlin.common import schema
from senlin.drivers import heat_v1 as heatclient
from senlin.engine import scheduler
from senlin.profiles import base

LOG = logging.getLogger(__name__)


class StackProfile(base.Profile):
    '''Profile for an OpenStack Heat stack.

    When this profile is used, the whole cluster is a collection of Heat
    stacks.
    '''

    KEYS = (
        TEMPLATE, CONTEXT, PARAMETERS, FILES,
        TIMEOUT, DISABLE_ROLLBACK, ENVIRONMENT,
    ) = (
        'template', 'context', 'parameters', 'files',
        'timeout', 'disable_rollback', 'environment',
    )

    spec_schema = {
        CONTEXT: schema.Map(
            _('A dictionary for specifying the customized context for '
              'stack operations'),
            default={},
        ),
        TEMPLATE: schema.Map(
            _('Heat stack template.'),
            required=True,
        ),
        PARAMETERS: schema.Map(
            _('Parameters to be passed to Heat for stack operations.'),
            default={},
        ),
        FILES: schema.Map(
            _('Contents of files referenced by the template, if any.'),
            default={},
        ),
        TIMEOUT: schema.Integer(
            _('A integer that specifies the number of minutes that a '
              'stack operation times out.'),
        ),
        DISABLE_ROLLBACK: schema.Boolean(
            _('A boolean specifying whether a stack operation can be '
              'rolled back.'),
            default=True,
        ),
        ENVIRONMENT: schema.Map(
            _('A map that specifies the environment used for stack '
              'operations.'),
            default={},
        )
    }

    def __init__(self, type_name, name, **kwargs):
        super(StackProfile, self).__init__(type_name, name, **kwargs)

        self.hc = None
        self.stack_id = None

    def heat(self):
        '''Construct heat client using the combined context.'''

        if self.hc:
            return self.hc

        stack_context = self.spec_data[self.CONTEXT]
        if stack_context is not None:
            ctx = self.context.to_dict()
            ctx.update(stack_context)
            self.context = context.RequestContext.from_dict(ctx)

        self.hc = heatclient.HeatClient(self.context)
        return self.hc

    def do_validate(self, obj):
        '''Validate if the spec has provided info for stack creation.'''

        kwargs = {
            'stack_name': obj.name,
            'template': self.spec_data[self.TEMPLATE],
            'timeout_mins': self.spec_data[self.TIMEOUT],
            'disable_rollback': self.spec_data[self.DISABLE_ROLLBACK],
            'parameters': self.spec_data[self.PARAMETERS],
            'files': self.spec_data[self.FILES],
            'environment': self.spec_data[self.ENVIRONMENT],
        }
        try:
            self.heat().stacks.validate(**kwargs)
        except Exception as ex:
            msg = _('Failed validate stack template due to '
                    '"%s"') % six.text_type(ex)
            raise exception.ProfileValidationFailed(message=msg)

        return True

    def _check_action_complete(self, obj, action):
        stack = self.heat().stack_get(id=self.stack_id)
        status = stack.stack_status.split('_', 1)

        if status[0] == action:
            if status[1] == 'IN_PROGRESS':
                return False

            if status[1] == 'COMPLETE':
                return True

            if status[1] == 'FAILED':
                raise exception.NodeStatusError(
                    status=stack.stack_status,
                    reason=stack.stack_status_reason)
            else:
                raise exception.NodeStatusError(
                    status=stack.stack_status,
                    reason=stack.stack_status_reason)
        else:
            msg = _('Node action mismatch detected: expected=%(expected)s '
                    'actual=%(actual)s') % dict(expected=action,
                                                actual=status[0])
            raise exception.NodeStatusError(status=stack.stack_status,
                                            reason=msg)

    def do_create(self, obj):
        '''Create a stack using the given profile.'''

        kwargs = {
            'stack_name': obj.name,
            'template': self.spec_data[self.TEMPLATE],
            'timeout_mins': self.spec_data[self.TIMEOUT],
            'disable_rollback': self.spec_data[self.DISABLE_ROLLBACK],
            'parameters': self.spec_data[self.PARAMETERS],
            'files': self.spec_data[self.FILES],
            'environment': self.spec_data[self.ENVIRONMENT],
        }

        LOG.info('Creating stack: %s' % kwargs)
        stack = self.heat().stack_create(**kwargs)
        self.stack_id = stack.id

        # Wait for action to complete/fail
        while not self._check_action_complete(obj, 'CREATE'):
            scheduler.sleep(1)

        return stack.id

    def do_delete(self, obj):
        self.stack_id = obj.physical_id

        try:
            self.heat().stack_delete(id=self.stack_id)
        except Exception as ex:
            raise ex

        # Wait for action to complete/fail
        while not self._check_action_complete(obj, 'DELETE'):
            scheduler.sleep(1)

        return True

    def do_update(self, obj, new_profile):
        '''Perform update on object.

        :param obj: the node object to operate on
        :param new_profile: the new profile used for updating
        '''
        self.stack_id = obj.physical_id
        if not self.stack_id:
            return True

        # TODO(anyone): Check if template differs
        # TODO(anyone): Check if params differs
        fields = {
            'stack_id': self.stack_id,
            'parameters': new_profile.spec_data[new_profile.PARAMETERS],
            'template': new_profile.spec_data[new_profile.TEMPLATE],
            'timeout_mins': new_profile.spec_data[new_profile.TIMEOUT],
            'disable_rollback': new_profile.spec_data[
                new_profile.DISABLE_ROLLBACK],
            'files': new_profile.spec_data[new_profile.FILES],
            'environment': new_profile.spec_data[new_profile.ENVIRONMENT],
        }

        self.heat().stacks.update(**fields)

        # Wait for action to complete/fail
        while not self._check_action_complete(obj, 'UPDATE'):
            scheduler.sleep(1)

        return True

    def do_check(self, obj):
        #TODO(anyone):
        #Use heat client to query stack status
        return True

    def get_template(self):
        return {}

    def get_schema(self):
        return {}
