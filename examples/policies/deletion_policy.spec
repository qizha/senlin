# Sample deletion policy that can be attached to a cluster.

# The valid values include:
# OLDEST_FIRST, OLDEST_PROFILE_FIRST, YOUNGEST_FIRST, RANDOM
criteria: OLDEST_FIRST

# Whether deleted node should be destroyed 
destroy_after_deletion: True

# Length in number of seconds before the actual deletion happens
# This param buys an instance some time before deletion
grace_period: 60

# Whether the deletion will reduce the desired capability of
# the cluster as well.
reduce_desired_capacity: False
