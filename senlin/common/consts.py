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

RPC_ATTRS = (
    ENGINE_TOPIC,
    ENGINE_DISPATCHER_TOPIC,
    RPC_API_VERSION,
) = (
    'senlin-engine',
    'engine-dispatcher',
    '1.0',
)

RPC_PARAMS = (
    PARAM_SHOW_DELETED, PARAM_SHOW_NESTED, PARAM_LIMIT, PARAM_GLOBAL_TENANT,
) = (
    'show_deleted', 'show_nested', 'limit', 'global_tenant',
)

ACTION_NAMES = (
    CLUSTER_CREATE, CLUSTER_DELETE, CLUSTER_UPDATE,
    CLUSTER_ADD_NODES, CLUSTER_DEL_NODES,
    CLUSTER_SCALE_OUT, CLUSTER_SCALE_IN,
    CLUSTER_ATTACH_POLICY, CLUSTER_DETACH_POLICY, CLUSTER_UPDATE_POLICY,

    NODE_CREATE, NODE_DELETE, NODE_UPDATE,
    NODE_JOIN, NODE_LEAVE,

    POLICY_ENABLE, POLICY_DISABLE, POLICY_UPDATE,
) = (
    'CLUSTER_CREATE', 'CLUSTER_DELETE', 'CLUSTER_UPDATE',
    'CLUSTER_ADD_NODES', 'CLUSTER_DEL_NODES',
    'CLUSTER_SCALE_OUT', 'CLUSTER_SCALE_IN',
    'CLUSTER_ATTACH_POLICY', 'CLUSTER_DETACH_POLICY', 'CLUSTER_UPDATE_POLICY',

    'NODE_CREATE', 'NODE_DELETE', 'NODE_UPDATE',
    'NODE_JOIN', 'NODE_LEAVE',

    'POLICY_ENABLE', 'POLICY_DISABLE', 'POLICY_UPDATE',
)


CLUSTER_ATTRS = (
    CLUSTER_NAME, CLUSTER_PROFILE, CLUSTER_SIZE,
    CLUSTER_ID, CLUSTER_PARENT,
    CLUSTER_DOMAIN, CLUSTER_PROJECT, CLUSTER_USER,
    CLUSTER_CREATED_TIME, CLUSTER_UPDATED_TIME, CLUSTER_DELETED_TIME,
    CLUSTER_STATUS, CLUSTER_STATUS_REASON, CLUSTER_TIMEOUT,
    CLUSTER_TAGS,
) = (
    'name', 'profile_id', 'size',
    'id', 'parent',
    'domain', 'project', 'user',
    'created_time', 'updated_time', 'deleted_time',
    'status', 'status_reason', 'timeout',
    'tags',
)

NODE_ATTRS = (
    NODE_INDEX, NODE_NAME, NODE_PROFILE_ID, NODE_CLUSTER_ID,
    NODE_CREATED_TIME, NODE_UPDATED_TIME, NODE_DELETED_TIME,
    NODE_STATUS, NODE_ROLE, NODE_TAGS,
) = (
    'index', 'name', 'profile_id', 'cluster_id',
    'created_time', 'updated_time', 'deleted_time',
    'status', 'role', 'tags',
)

PROFILE_ATTRS = (
    PROFILE_ID, PROFILE_NAME, PROFILE_TYPE, PROFILE_PERMISSION,
    PROFILE_CREATED_TIME, PROFILE_UPDATED_TIME, PROFILE_DELETED_TIME,
    PROFILE_SPEC, PROFILE_TAGS,
) = (
    'id', 'name', 'type', 'permission',
    'created_time', 'updated_time', 'deleted_time',
    'spec', 'tags',
)

POLICY_ATTRS = (
    POLICY_ID, POLICY_NAME, POLICY_TYPE,
    POLICY_SPEC, POLICY_LEVEL, POLICY_COOLDOWN,
    POLICY_CREATED_TIME, POLICY_UPDATED_TIME, POLICY_DELETED_TIME,
) = (
    'id', 'name', 'type',
    'spec', 'level', 'cooldown',
    'created_time', 'updated_time', 'deleted_time',
)

CLUSTER_POLICY_ATTRS = (
    CP_POLICY_ID, CP_PRIORITY, CP_LEVEL, CP_COOLDOWN, CP_ENABLED,
) = (
    'policy_id', 'priority', 'level', 'cooldown', 'enabled',
)

EVENT_ATTRS = (
    EVENT_TIMESTAMP, EVENT_OBJ_ID, EVENT_OBJ_NAME, EVENT_OBJ_TYPE,
    EVENT_USER, EVENT_ACTION, EVENT_STATUS, EVENT_STATUS_REASON,
) = (
    'timestamp', 'obj_id', 'obj_name', 'obj_type',
    'user', 'action', 'status', 'status_reason',
)

ACTION_ATTRS = (
    ACTION_NAME, ACTION_TARGET, ACTION_ACTION, ACTION_CAUSE,
    ACTION_INTERVAL, ACTION_START_TIME, ACTION_END_TIME,
    ACTION_TIMEOUT, ACTION_STATUS, ACTION_STATUS_REASON,
    ACTION_INPUTS, ACTION_OUTPUTS, ACTION_DEPENDS_ON, ACTION_DEPENDED_BY,
) = (
    'name', 'target', 'action', 'cause',
    'interval', 'start_time', 'end_time',
    'timeout', 'status', 'status_reason',
    'inputs', 'outputs', 'depends_on', 'depended_by',
)
