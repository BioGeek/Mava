# python3
# Copyright 2021 InstaDeep Ltd. All rights reserved.
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

import random
from datetime import datetime
from typing import Any, Callable, Dict

import sonnet as snt
from absl import app, flags
from acme import specs as acme_specs

from mava import specs as mava_specs
from mava.components.tf.modules.exploration.exploration_scheduling import (
    LinearExplorationScheduler,
)
from mava.core import Executor
from mava.environment_loop import ParallelEnvironmentLoop
from mava.systems.tf import madqn
from mava.utils import loggers, lp_utils
from mava.utils.environments.meltingpot_utils.env_utils import (
    MeltingPotEnvironmentFactory,
    scenarios_for_substrate,
)
from mava.utils.environments.meltingpot_utils.evaluation_utils import (
    AgentNetworks,
    MAVASystem,
    ScenarioEvaluation,
)
from mava.utils.environments.meltingpot_utils.network_utils import (
    make_default_madqn_networks,
)
from mava.utils.loggers import logger_utils

FLAGS = flags.FLAGS

flags.DEFINE_string(
    "mava_id",
    str(datetime.now()),
    "Experiment identifier that can be used to continue experiments.",
)
flags.DEFINE_string("logdir", "./logs", "Base dir to store experiments.")
flags.DEFINE_string(
    "checkpoint_dir", "", "directory where checkpoints were saved during training"
)
flags.DEFINE_string("substrate", "clean_up", "scenario to evaluste on")


def madqn_evaluation_loop_creator(system: MAVASystem) -> ParallelEnvironmentLoop:
    """Creates an environment loop for the evaluation of a system

    Args:
        system ([MAVASystem]): the system to evaluate

    Returns:
        [ParallelEnvironmentLoop]: an environment loop for evaluation
    """
    evaluator_loop = system.evaluator(system.variable_server())
    return evaluator_loop


def get_trained_madqn_networks(
    substrate: str,
    network_factory: Callable[[acme_specs.BoundedArray], Dict[str, snt.Module]],
    checkpoint_dir: str,
) -> Dict[str, snt.Module]:
    """Obtains madqn networks trained on the substrate

    Args:
        substrate (str): substrate in which the networks were trained
        network_factory: creates the networks given the environment spec
        checkpoint_dir (str): checkpoint directory from which to restore network weights

    Returns:
        Dict[str, snt.Module]: trained networks
    """
    substrate_environment_factory = MeltingPotEnvironmentFactory(substrate=substrate)
    system = madqn.MADQN(
        environment_factory=substrate_environment_factory,
        network_factory=network_factory,
        exploration_scheduler_fn=LinearExplorationScheduler(
            epsilon_min=0.05, epsilon_decay=1e-4
        ),
        checkpoint_subpath=checkpoint_dir,
        shared_weights=False,
    )
    networks = system.create_system()
    variables = system.variable_server().variables
    for net_type_key in networks:
        for net_key in networks[net_type_key]:
            for var_i in range(len(variables[f"{net_key}_{net_type_key}"])):
                networks[net_type_key][net_key].variables[var_i].assign(variables[f"{net_key}_{net_type_key}"][var_i])
    return networks  # type: ignore


def madqn_agent_network_setter(
    evaluator: Executor, trained_networks: Dict[str, Any]
) -> None:
    """Sets the networks for agents in the evaluator

    This is done by sampling from the trained networks

    Args:
        evaluator (Executor): [description]
        trained_networks (Dict[str, Any]): [description]
    """
    observation_networks = trained_networks["observations"]
    value_networks = trained_networks["values"]
    selectors = trained_networks["selectors"]
    
    # network keys
    trained_network_keys = list(trained_networks["observations"].keys())
    network_keys = evaluator._observation_networks.keys()
    
    for key in network_keys:
        # sample a trained network
        idx = random.randint(0, len(trained_network_keys) - 1)
        
        # observation networks
        evaluator._observation_networks[key]=observation_networks[trained_network_keys[idx]]
        
        # value networks
        evaluator._value_networks[key]=value_networks[trained_network_keys[idx]]
        
        # selectors
        evaluator._action_selectors[key]=selectors[trained_network_keys[idx]]


def evaluate_on_scenarios(substrate: str, checkpoint_dir: str) -> None:
    """Tests the system on all the scenarios associated with the specified substrate

    Args:
        substrate: the name of the substrate for which scenarios would be created
        checkpoint_dir: directory where checkpoint is to be restored from
    """
    scenarios = scenarios_for_substrate(substrate)

    # Networks.
    network_factory = lp_utils.partial_kwargs(make_default_madqn_networks)

    trained_networks = get_trained_madqn_networks(
        substrate, network_factory, checkpoint_dir
    )

    for scenario in scenarios:
        evaluate_on_scenario(scenario, network_factory, trained_networks)


def evaluate_on_scenario(
    scenario_name: str,
    network_factory: Callable[[mava_specs.MAEnvironmentSpec], AgentNetworks],
    trained_networks: AgentNetworks,
) -> None:
    """Evaluates a system on a scenario using already trained networks

    Args:
        scenario_name: name of scenario in which system would be evaluated
        network_factory: for instantiating the agent networks for the system
        trained_networks: agent networks previously trained on the corresponding
            substrate

    """
    # Scenario Environment.
    scenario_environment_factory = MeltingPotEnvironmentFactory(scenario=scenario_name)

    # Log every [log_every] seconds.
    log_every = 10

    def logger_factory(label: str, **kwargs: Any) -> loggers.Logger:
        logger = logger_utils.make_logger(
            scenario_name,
            directory=FLAGS.logdir,
            to_terminal=True,
            to_tensorboard=True,
            time_stamp=FLAGS.mava_id,
            time_delta=log_every,
        )
        return logger

    # Create madqn system for scenario
    scenario_system = madqn.MADQN(
        environment_factory=scenario_environment_factory,
        network_factory=network_factory,
        logger_factory=logger_factory,
        exploration_scheduler_fn=LinearExplorationScheduler(
            epsilon_min=0.05, epsilon_decay=1e-4
        ),
        shared_weights=False,
    )

    # Evaluation loop
    evaluation_loop = ScenarioEvaluation(
        scenario_system,
        madqn_evaluation_loop_creator,
        madqn_agent_network_setter,
        trained_networks,
    )
    evaluation_loop.run()


def main(_: Any) -> None:
    """Evaluate on a scenario

    Args:
        _ (Any): ...
    """
    evaluate_on_scenarios(FLAGS.substrate, FLAGS.checkpoint_dir)


if __name__ == "__main__":
    app.run(main)
