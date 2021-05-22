# python3
# Copyright 2021 [...placeholder...]. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# TODO (Kevin): implement DIAL executor (if required)
# Helper resources
#   - single agent generic actors in acme:
#           https://github.com/deepmind/acme/blob/master/acme/agents/tf/actors.py
#   - single agent custom actor for Impala in acme:
#           https://github.com/deepmind/acme/blob/master/acme/agents/tf/impala/acting.py
#   - multi-agent generic executors in mava: mava/systems/tf/executors.py

"""DIAL executor implementation."""
from typing import Any, Dict, Optional

import sonnet as snt
from acme.tf import variable_utils as tf2_variable_utils

from mava import adders
from mava.components.tf.modules.communication import BaseCommunicationModule
from mava.systems.tf.madqn.execution import MADQNRecurrentCommExecutor
from mava.systems.tf.madqn.training import MADQNTrainer


class DIALExecutor(MADQNRecurrentCommExecutor):
    """DIAL executor.
    An executor based on a recurrent communicating policy for each agent in the system
    which takes non-batched observations and outputs non-batched actions.
    It also allows adding experiences to replay and updating the weights
    from the policy on the learner.
    """

    def __init__(
        self,
        q_networks: Dict[str, snt.Module],
        action_selectors: Dict[str, snt.Module],
        communication_module: BaseCommunicationModule,
        shared_weights: bool = True,
        adder: Optional[adders.ParallelAdder] = None,
        variable_client: Optional[tf2_variable_utils.VariableClient] = None,
        store_recurrent_state: bool = True,
        trainer: MADQNTrainer = None,
        fingerprint: bool = False,
        evaluator: bool = False,
    ):
        """Initializes the executor.
        Args:
          policy_network: the policy to run for each agent in the system.
          shared_weights: specify if weights are shared between agent networks.
          adder: the adder object to which allows to add experiences to a
            dataset/replay buffer.
          variable_client: object which allows to copy weights from the trainer copy
            of the policies to the executor copy (in case they are separate).
        """

        # Store these for later use.
        self._adder = adder
        self._variable_client = variable_client
        self._q_networks = q_networks
        self._policy_networks = q_networks
        self._communication_module = communication_module
        self._action_selectors = action_selectors
        self._store_recurrent_state = store_recurrent_state
        self._trainer = trainer
        self._shared_weights = shared_weights

        self._states: Dict[str, Any] = {}
        self._messages: Dict[str, Any] = {}
