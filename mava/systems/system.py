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

"""MADDPG system implementation."""

from typing import Any, Dict, List, Tuple

import acme
import launchpad as lp
import reverb
import sonnet as snt
from acme.utils import loggers


import mava
from mava.callbacks.base import Callback

from mava.systems.tf.variable_sources import VariableSource as MavaVariableSource
from mava.wrappers import DetailedPerAgentStatistics


class System:
    """MARL system."""

    def __init__(
        self,
        config: Dict[str, Dict[str, Any]],
        components: Dict[str, Dict[str, Callback]],
    ):
        """[summary]

        Args:
            config (Dict[str, Dict[str, Any]]): [description]
            components (Dict[str, Dict[str, Callback]]): [description]
        """

        self.config = config
        self.components = components

        self.callbacks = []
        for system_components in components.values():
            for component in system_components.values():
                self.callbacks.append(component)

        self.on_building_init_start(self)

        self.on_building_init(self)

        self.on_building_init_end(self)

    def tables(self) -> List[reverb.Table]:
        """ "Create tables to insert data into.
        Args:
            environment_spec (specs.MAEnvironmentSpec): description of the action and
                observation spaces etc. for each agent in the system.
        Raises:
            NotImplementedError: unknown executor type.
        Returns:
            List[reverb.Table]: a list of data tables for inserting data.
        """

        # start of make replay tables
        self.on_building_tables_start(self)

        # make adder signature
        self.on_building_tables_adder_signature(self)

        # make rate limiter
        self.on_building_tables_rate_limiter(self)

        # make tables
        self.on_building_tables(self)

        # end of make replay tables
        self.on_building_tables_end(self)

        return self.tables

    def system(
        self,
    ) -> Tuple[Dict[str, Dict[str, snt.Module]], Dict[str, Dict[str, snt.Module]]]:
        """Initialise the system variables from the network factory."""

        self.on_building_system_start(self)

        self.on_building_system_networks(self)

        self.on_building_system_architecture(self)

        self.on_building_system(self)

        self.on_building_system_end(self)

        # Create system architecture with target networks.
        # adder_env_spec = self._builder.convert_discrete_to_bounded(
        #     self._environment_spec
        # )

        # net_spec_keys is only implemented for the Decentralised architectures
        # if (
        #     self._architecture == DecentralisedValueActorCritic
        #     or self._architecture == DecentralisedQValueActorCritic
        # ):
        #     architecture_config["net_spec_keys"] = self._net_spec_keys

        return self.system_networks

    def variable_server(self) -> MavaVariableSource:
        """Create the variable server.
        Args:
            networks (Dict[str, Dict[str, snt.Module]]): dictionary with the
            system's networks in.
        Returns:
            variable_source (MavaVariableSource): A Mava variable source object.
        """

        # start of make variable server
        self.on_building_variable_server_start(self)

        # make variable server
        self.on_building_variable_server(self)

        # end of make variable server
        self.on_building_variable_server_end(self)

        return self.variable_server

    def executor(
        self,
        executor_id: str,
        replay: reverb.Client,
        variable_source: acme.VariableSource,
    ) -> mava.ParallelEnvironmentLoop:
        """System executor
        Args:
            executor_id (str): id to identify the executor process for logging purposes.
            replay (reverb.Client): replay data table to push data to.
            variable_source (acme.VariableSource): variable server for updating
                network variables.
            counter (counting.Counter): step counter object.
        Returns:
            mava.ParallelEnvironmentLoop: environment-executor loop instance.
        """

        self.on_building_executor_start(self)

        self.on_building_executor_logger(self)

        self.on_building_executor(self)

        self.on_building_executor_train_loop(self)

        self.on_building_executor_end(self)

        # Create the system
        behaviour_policy_networks, networks = self.create_system()

        # Create the executor.
        executor = self._builder.make_executor(
            networks=networks,
            policy_networks=behaviour_policy_networks,
            adder=self._builder.make_adder(replay),
            variable_source=variable_source,
        )

        # TODO (Arnu): figure out why factory function are giving type errors
        # Create the environment.
        environment = self._environment_factory(evaluation=False)  # type: ignore

        # Create executor logger
        executor_logger_config = {}
        if self._logger_config and "executor" in self._logger_config:
            executor_logger_config = self._logger_config["executor"]
        exec_logger = self._logger_factory(  # type: ignore
            f"executor_{executor_id}", **executor_logger_config
        )

        # Create the loop to connect environment and executor.
        train_loop = self._train_loop_fn(
            environment,
            executor,
            logger=exec_logger,
            **self._train_loop_fn_kwargs,
        )

        train_loop = DetailedPerAgentStatistics(train_loop)

        return train_loop

    def evaluator(
        self,
        variable_source: acme.VariableSource,
        logger: loggers.Logger = None,
    ) -> Any:
        """System evaluator (an executor process not connected to a dataset)
        Args:
            variable_source (acme.VariableSource): variable server for updating
                network variables.
            counter (counting.Counter): step counter object.
            logger (loggers.Logger, optional): logger object. Defaults to None.
        Returns:
            Any: environment-executor evaluation loop instance for evaluating the
                performance of a system.
        """

        # Create the system
        behaviour_policy_networks, networks = self.create_system()

        # Create the agent.
        executor = self._builder.make_executor(
            # executor_id="evaluator",
            networks=networks,
            policy_networks=behaviour_policy_networks,
            variable_source=variable_source,
        )

        # Make the environment.
        environment = self._environment_factory(evaluation=True)  # type: ignore

        # Create logger and counter.
        evaluator_logger_config = {}
        if self._logger_config and "evaluator" in self._logger_config:
            evaluator_logger_config = self._logger_config["evaluator"]
        eval_logger = self._logger_factory(  # type: ignore
            "evaluator", **evaluator_logger_config
        )

        # Create the run loop and return it.
        # Create the loop to connect environment and executor.
        eval_loop = self._eval_loop_fn(
            environment,
            executor,
            logger=eval_logger,
            **self._eval_loop_fn_kwargs,
        )

        eval_loop = DetailedPerAgentStatistics(eval_loop)
        return eval_loop

    def trainer(
        self,
        trainer_id: str,
        replay: reverb.Client,
        variable_source: MavaVariableSource,
        # counter: counting.Counter,
    ) -> mava.core.Trainer:
        """System trainer
        Args:
            replay (reverb.Client): replay data table to pull data from.
            counter (counting.Counter): step counter object.
        Returns:
            mava.core.Trainer: system trainer.
        """

        # create logger
        trainer_logger_config = {}
        if self._logger_config and "trainer" in self._logger_config:
            trainer_logger_config = self._logger_config["trainer"]
        trainer_logger = self._logger_factory(  # type: ignore
            f"trainer_{trainer_id}", **trainer_logger_config
        )

        # Create the system
        _, networks = self.create_system()

        dataset = self._builder.make_dataset_iterator(
            replay, f"{self._builder._config.replay_table_name}_{trainer_id}"
        )

        return self._builder.make_trainer(
            # trainer_id=trainer_id,
            networks=networks,
            trainer_networks=self._trainer_networks[f"trainer_{trainer_id}"],
            trainer_table_entry=self._table_network_config[f"trainer_{trainer_id}"],
            dataset=dataset,
            logger=trainer_logger,
            variable_source=variable_source,
        )

    def build(self, name: str = "maddpg") -> Any:
        """Build the distributed system as a graph program.
        Args:
            name (str, optional): system name. Defaults to "maddpg".
        Returns:
            Any: graph program for distributed system training.
        """
        program = lp.Program(name=name)

        with program.group("replay"):
            replay = program.add_node(lp.ReverbNode(self.replay))

        with program.group("variable_server"):
            variable_server = program.add_node(lp.CourierNode(self.variable_server))

        with program.group("trainer"):
            # Add executors which pull round-robin from our variable sources.
            for trainer_id in range(len(self._trainer_networks.keys())):
                program.add_node(
                    lp.CourierNode(self.trainer, trainer_id, replay, variable_server)
                )

        with program.group("evaluator"):
            program.add_node(lp.CourierNode(self.evaluator, variable_server))

        with program.group("executor"):
            # Add executors which pull round-robin from our variable sources.
            for executor_id in range(self._num_exectors):
                program.add_node(
                    lp.CourierNode(self.executor, executor_id, replay, variable_server)
                )

        return program
