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

import random

from oslo_log import log as logging

from senlin.common import consts
from senlin.common import exception
from senlin.common.i18n import _
from senlin.common.i18n import _LE
from senlin.db import api as db_api
from senlin.engine.actions import base
from senlin.engine import cluster as cluster_mod
from senlin.engine import dispatcher
from senlin.engine import node as node_mod
from senlin.engine import scheduler
from senlin.engine import senlin_lock
from senlin.policies import base as policy_mod

LOG = logging.getLogger(__name__)


class ClusterAction(base.Action):
    '''An action performed on a cluster.'''

    ACTIONS = (
        CLUSTER_CREATE, CLUSTER_DELETE, CLUSTER_UPDATE,
        CLUSTER_ADD_NODES, CLUSTER_DEL_NODES,
        CLUSTER_SCALE_OUT, CLUSTER_SCALE_IN,
        CLUSTER_ATTACH_POLICY, CLUSTER_DETACH_POLICY, CLUSTER_UPDATE_POLICY
    ) = (
        consts.CLUSTER_CREATE, consts.CLUSTER_DELETE, consts.CLUSTER_UPDATE,
        consts.CLUSTER_ADD_NODES, consts.CLUSTER_DEL_NODES,
        consts.CLUSTER_SCALE_OUT, consts.CLUSTER_SCALE_IN,
        consts.CLUSTER_ATTACH_POLICY, consts.CLUSTER_DETACH_POLICY,
        consts.CLUSTER_UPDATE_POLICY,
    )

    def __init__(self, context, action, **kwargs):
        super(ClusterAction, self).__init__(context, action, **kwargs)

    def _wait_for_dependents(self):
        self.get_status()
        reason = ''
        while self.status != self.READY:
            if self.status == self.FAILED:
                reason = _('%(action)s [%(id)s] failed due to dependent '
                           'action failure') % {'action': self.action,
                                                'id': self.id}
                LOG.debug(reason)
                return self.RES_ERROR, reason

            if self.is_cancelled():
                # During this period, if cancel request come, cancel this
                # cluster operation immediately, then release the cluster
                # lock and return.
                reason = _('%(action)s %(id)s cancelled') % {
                    'action': self.action, 'id': self.id}
                LOG.debug(reason)
                return self.RES_CANCEL, reason

            if self.is_timeout():
                # Action timeout, return
                reason = _('%(action)s %(id)s timeout') % {
                    'action': self.action, 'id': self.id}
                LOG.debug(reason)
                return self.RES_TIMEOUT

            # Continue waiting (with reschedule)
            scheduler.reschedule(self, 1)
            self.get_status()

        return self.RES_OK, 'All dependents ended with success'

    def _create_nodes(self, cluster, count, policy_data):
        '''Utility method for node creation.'''
        placement = policy_data.get('placement', None)

        for m in range(count):
            name = 'node-%s-%003d' % (cluster.id[:8], cluster.size + m + 1)
            node = node_mod.Node(name, cluster.profile_id, cluster.id,
                                 context=self.context)

            if placement is not None:
                # We assume placement is a list
                node.data['placement'] = placement[m]
            node.store(self.context)

            kwargs = {
                'name': 'node_create_%s' % node.id[:8],
                'target': node.id,
                'cause': base.CAUSE_DERIVED,
            }

            action = base.Action(self.context, 'NODE_CREATE', **kwargs)
            action.store(self.context)

            # Build dependency and make the new action ready
            db_api.action_add_dependency(self.context, action.id, self.id)
            action.set_status(self.READY)

            dispatcher.notify(self.context, dispatcher.Dispatcher.NEW_ACTION,
                              None, action_id=action.id)

        if count > 0:
            # Wait for cluster creation to complete
            return self._wait_for_dependents()

        return self.RES_OK, ''

    def do_create(self, cluster, policy_data):
        res = cluster.do_create(self.context)

        if not res:
            reason = 'Cluster creation failed.'
            cluster.set_status(cluster.ERROR, reason)
            return self.RES_ERROR, reason

        result, reason = self._create_nodes(cluster, cluster.size, policy_data)

        if result == self.RES_OK:
            reason = 'Cluster creation succeeded'
            cluster.set_status(self.context, cluster.ACTIVE, reason)
        elif result in [self.RES_CANCEL, self.RES_TIMEOUT, self.RES_ERROR]:
            cluster.set_status(self.context, cluster.ERROR, reason)
        else:
            # RETRY or FAILED?
            pass

        return result, reason

    def do_update(self, cluster, policy_data):
        reason = 'Cluster update succeeded'
        new_profile_id = self.inputs.get('new_profile_id')
        res = cluster.do_update(self.context, profile_id=new_profile_id)
        if not res:
            reason = 'Cluster object cannot be updated.'
            # Reset status to active
            cluster.set_status(cluster.ACTIVE, reason)
            return self.RES_ERROR

        # Create NodeActions for all nodes
        node_list = cluster.get_nodes()
        for node_id in node_list:
            kwargs = {
                'name': 'node_update_%s' % node_id[:8],
                'target': node_id,
                'cause': base.CAUSE_DERIVED,
                'inputs': {
                    'new_profile_id': new_profile_id,
                }
            }
            action = base.Action(self.context, 'NODE_UPDATE', **kwargs)
            action.store(self.context)

            db_api.action_add_dependency(action, self)
            action.set_status(self.READY)
            dispatcher.notify(self.context, dispatcher.Dispatcher.NEW_ACTION,
                              None, action_id=action.id)

        # Wait for cluster updating complete
        result = self.RES_OK
        if cluster.size > 0:
            result, reason = self._wait_for_dependents()

        if result == self.RES_OK:
            cluster.set_status(self.context, cluster.ACTIVE, reason)

        return result, reason

    def _delete_nodes(self, cluster, nodes, policy_data):
        action_name = consts.NODE_DELETE

        pd = policy_data.get('deletion', None)
        if pd is not None:
            destroy = pd.get('destroy_after_delete', True)
            if not destroy:
                action_name = consts.NODE_LEAVE

        for node_id in nodes:
            action = base.Action(self.context, action_name,
                                 name='node_delete_%s' % node_id[:8],
                                 target=node_id,
                                 cause=base.CAUSE_DERIVED)
            action.store(self.context)

            # Build dependency and make the new action ready
            db_api.action_add_dependency(self.context, action.id, self.id)
            action.set_status(self.READY)

            dispatcher.notify(self.context, dispatcher.Dispatcher.NEW_ACTION,
                              None, action_id=action.id)

        if len(nodes) > 0:
            return self._wait_for_dependents()

        return self.RES_OK, ''

    def do_delete(self, cluster, policy_data):
        reason = 'Deletion in progress'
        cluster.set_status(self.context, cluster.DELETING, reason)
        nodes = [node.id for node in cluster.get_nodes()]

        # For cluster delete, we delete the nodes
        data = {
            'deletion': {
                'destroy_after_delete': True
            }
        }
        policy_data.update(data)
        result, reason = self._delete_nodes(cluster, nodes, policy_data)

        if result == self.RES_OK:
            res = cluster.do_delete(self.context)
            if not res:
                return self.RES_ERROR, 'Cannot delete cluster object.'
        elif result in [self.RES_CANCEL, self.RES_TIMEOUT, self.RES_ERROR]:
            cluster.set_status(self.context, cluster.ACTIVE, reason)
        else:
            # RETRY
            pass

        return result, reason

    def do_add_nodes(self, cluster, policy_data):
        nodes = self.inputs.get('nodes')

        # NOTE: node states might have changed before we lock the cluster
        failures = {}
        for node_id in nodes:
            try:
                node = node_mod.Node.load(self.context, node_id)
            except exception.NodeNotFound:
                failures[node_id] = 'Node not found'
                continue

            if node.cluster_id == cluster.id:
                nodes.remove(node_id)
                continue

            if node.cluster_id is not None:
                failures[node_id] = _('Node already owned by cluster '
                                      '%s') % node.cluster_id
                continue
            if node.status != node_mod.Node.ACTIVE:
                failures[node_id] = _('Node not in ACTIVE status')
                continue

            # check profile type matching
            node_profile_type = node.rt['profile'].type
            cluster_profile_type = cluster.rt['profile'].type
            if node_profile_type != cluster_profile_type:
                failures[node.id] = 'Profile type does not match'
                continue

        if len(failures) > 0:
            return self.RES_ERROR, str(failures)

        reason = 'Completed adding nodes'
        if len(nodes) == 0:
            return self.RES_OK, reason

        for node_id in nodes:
            action = base.Action(self.context, 'NODE_JOIN',
                                 name='node_join_%s' % node.id[:8],
                                 target=node.id,
                                 cause=base.CAUSE_DERIVED,
                                 inputs={'cluster_id': cluster.id})
            action.store(self.context)
            db_api.action_add_dependency(self.context, action.id, self.id)
            action.set_status(self.READY)
            dispatcher.notify(self.context, dispatcher.Dispatcher.NEW_ACTION,
                              None, action_id=action.id)

        # Wait for dependent action if any
        result, new_reason = self._wait_for_dependents()
        if result != self.RES_OK:
            reason = new_reason
        return result, reason

    def do_del_nodes(self, cluster, policy_data):
        nodes = self.inputs.get('nodes')

        # NOTE: node states might have changed before we lock the cluster
        failures = {}
        for node_id in nodes:
            try:
                node = node_mod.Node.load(self.context, node_id)
            except exception.NodeNotFound:
                failures[node_id] = 'Node not found'
                continue

            if node.cluster_id is None:
                nodes.remove(node_id)

        if len(failures) > 0:
            return self.RES_ERROR, str(failures)

        reason = 'Completed deleting nodes'
        if len(nodes) == 0:
            return self.RES_OK, reason

        # For deleting nodes from cluster, set destroy to false
        data = {
            'deletion': {
                'destroy_after_delete': False,
            }
        }
        policy_data.update(data)
        result, new_reason = self._delete_nodes(cluster, nodes, policy_data)

        if result != self.RES_OK:
            reason = new_reason
        return result, reason

    def do_scale_out(self, cluster, policy_data):
        # We may get a scale count from the request directly, if that is the
        # case, we will use it for scaling. Or else, we check if we have got
        # hints from policy checking. We use policy output if any, or else
        # the count is set to 1 as default.
        count = self.inputs.get('count', 0)
        if count == 0:
            pd = policy_data.get('creation', None)
            if pd is not None:
                count = pd.get('count', 1)

        if count == 0:
            return self.RES_OK, 'No scaling needed based on policy checking'

        if count > 0:
            result, reason = self._create_nodes(cluster, count, policy_data)
        else:
            candidates = []
            nodes = db_api.node_get_all_by_cluster(self.context, cluster.id)
            i = count
            while i > 0:
                r = random.randrange(len(nodes))
                candidates.append(nodes[r].id)
                nodes.remove(nodes[r])
                i = i - 1

            result, reason = self._delete_nodes(cluster, candidates,
                                                policy_data)

        if result == self.RES_OK:
            reason = 'Cluster scaling succeeded'
            cluster.set_status(self.context, cluster.ACTIVE, reason)
        elif result in [self.RES_CANCEL, self.RES_TIMEOUT, self.RES_FAILED]:
            cluster.set_status(self.context, cluster.ERROR, reason)
        else:
            # RETRY or FAILED?
            pass

        return result, reason

    def do_scale_in(self, cluster, policy_data):
        # We may get a scale count from the request directly, if that is the
        # case, we will use it for scaling. Or else, we check if we have got
        # hints from policy checking. We use policy output if any, or else
        # the count is set to 1 as default.
        count = self.inputs.get('count', 0)
        candidates = []
        if count == 0:
            pd = policy_data.get('deletion', None)
            if pd is not None:
                count = pd.get('count', 1)
                # Try get candidates (set by deletion policy if attached)
                candidates = policy_data.get('candidates', [])

        if count == 0:
            return self.RES_OK, 'No scaling needed based on policy checking'

        # Choose victims randomly
        if len(candidates) == 0:
            nodes = db_api.node_get_all_by_cluster(self.context, cluster.id)
            i = count
            while i > 0:
                r = random.randrange(len(nodes))
                candidates.append(nodes[r].id)
                nodes.remove(nodes[r])
                i = i - 1

        # The policy data may contain destroy flag and grace period option
        result, new_reason = self._delete_nodes(cluster, candidates,
                                                policy_data)

        if result == self.RES_OK:
            reason = 'Cluster scaling succeeded'
            cluster.set_status(self.context, cluster.ACTIVE, reason)
        elif result in [self.RES_CANCEL, self.RES_TIMEOUT, self.RES_FAILED]:
            cluster.set_status(self.context, cluster.ERROR, reason)
        else:
            # RETRY or FAILED?
            pass

        return result, reason

    def do_attach_policy(self, cluster, policy_data):
        '''Attach policy to the cluster.
        '''
        policy_id = self.inputs.get('policy_id', None)
        if not policy_id:
            raise exception.PolicyNotSpecified()

        policy = policy_mod.Policy.load(self.context, policy_id)
        # Check if policy has already been attached
        all = db_api.cluster_policy_get_all(self.context, cluster.id)
        for existing in all:
            # Policy already attached
            if existing.policy_id == policy_id:
                return self.RES_OK, 'Policy already attached'

            # Detect policy type conflicts
            curr = policy_mod.Policy.load(self.context, existing.policy_id)
            if curr.type == policy.type:
                raise exception.PolicyExists(policy_type=policy.type)

        res = policy.attach(self.context, cluster, policy_data)
        if not res:
            return self.RES_ERROR, 'Failed attaching policy'

        values = {
            'cooldown': self.inputs.get('cooldown', policy.cooldown),
            'level': self.inputs.get('level', policy.level),
            'priority': self.inputs.get('priority', 50),
            'enabled': self.inputs.get('enabled', True),
        }

        db_api.cluster_policy_attach(self.context, cluster.id, policy_id,
                                     values)

        cluster.attach(policy)
        return self.RES_OK, 'Policy attached'

    def do_detach_policy(self, cluster, policy_data):
        policy_id = self.inputs.get('policy_id', None)
        if not policy_id:
            raise exception.PolicyNotSpecified()

        policy = policy_mod.Policy.load(self.context, policy_id)
        res = policy.detach(self.context, cluster, policy_data)
        if not res:
            return self.RES_ERROR, 'Failed detaching policy'

        db_api.cluster_policy_detach(self.context, cluster.id, policy_id)

        cluster.detach(policy.policy_id)
        return self.RES_OK, 'Policy detached'

    def do_update_policy(self, cluster, policy_data):
        policy_id = self.inputs.get('policy_id', None)
        if not policy_id:
            raise exception.PolicyNotSpecified()

        values = {}
        cooldown = self.inputs.get('cooldown')
        if cooldown is not None:
            values['cooldown'] = cooldown
        level = self.inputs.get('level')
        if level is not None:
            values['level'] = level
        priority = self.inputs.get('priority')
        if priority is not None:
            values['priority'] = priority
        enabled = self.inputs.get('enabled')
        if enabled is not None:
            values['enabled'] = bool(enabled)

        db_api.cluster_policy_update(self.context, cluster.id, policy_id,
                                     values)

        return self.RES_OK, 'Policy updated'

    def _execute(self, cluster):
        # do pre-action policy checking
        pd = self.policy_check(cluster.id, 'BEFORE')
        if pd.status != policy_mod.CHECK_OK:
            return self.RES_ERROR, _('Policy failure: %s') % pd.reason

        result = self.RES_OK
        action_name = self.action.lower()
        method_name = action_name.replace('cluster', 'do')
        method = getattr(self, method_name)
        if method is None:
            raise exception.ActionNotSupported(action=self.action)

        result, reason = method(cluster, policy_data=pd)

        # do post-action policy checking
        if result == self.RES_OK:
            pd = self.policy_check(cluster.id, 'AFTER')
            if pd.status != policy_mod.CHECK_OK:
                return self.RES_ERROR, pd.reason

        return result, reason

    def execute(self, **kwargs):
        '''Wrapper of action execution.
        This is mainly a wrapper that executes an action with cluster lock
        acquired.
        :return: A tuple (res, reason) that indicates whether the execution
                 was a success and why if it wasn't a success.
        '''

        try:
            cluster = cluster_mod.Cluster.load(self.context, self.target)
        except exception.NotFound:
            reason = _('Cluster %(id)s not found') % {'id': self.target}
            LOG.error(_LE(reason))
            return self.RES_ERROR, reason

        # Try to lock cluster before do real operation
        forced = True if self.action == self.CLUSTER_DELETE else False
        res = senlin_lock.cluster_lock_acquire(cluster.id, self.id,
                                               senlin_lock.CLUSTER_SCOPE,
                                               forced)
        if not res:
            return self.RES_ERROR, _('Failed locking cluster')

        try:
            res, reason = self._execute(cluster)
        finally:
            senlin_lock.cluster_lock_release(cluster.id, self.id,
                                             senlin_lock.CLUSTER_SCOPE)

        return res, reason

    def cancel(self):
        return self.RES_OK
