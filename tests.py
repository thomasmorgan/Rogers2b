from __future__ import print_function
import sys
from wallace import db
from wallace.nodes import Agent, Source, Environment
from wallace.information import Gene, Meme, State
from experiment import RogersExperiment, RogersAgent, RogersAgentFounder, RogersSource, RogersEnvironment, LearningGene
import random
import traceback
from datetime import datetime


def timenow():
    """A string representing the current date and time."""
    return datetime.now()


class TestRogers(object):

    def setup(self):
        self.db = db.init_db(drop_all=True)

    def teardown(self):
        self.db.rollback()
        self.db.close()
        # os.remove('wallace.db')

    def add(self, *args):
        self.db.add_all(args)
        self.db.commit()

    def test_run_rogers(self):

        """
        SIMULATE ROGERS
        """

        overall_start_time = timenow()

        print("Running simulated experiment...", end="\r")
        sys.stdout.flush()

        exp_setup_start = timenow()
        exp = RogersExperiment(self.db)
        exp_setup_stop = timenow()

        exp_setup_start2 = timenow()
        exp = RogersExperiment(self.db)
        exp_setup_stop2 = timenow()

        p_uuids = []
        p_times = []
        dum = timenow()
        assign_time = dum - dum
        process_time = dum - dum

        while not exp.is_experiment_over():

            num_completed_participants = len(exp.networks()[0].nodes(type=Agent))

            print("Running simulated experiment... participant {} of {}, {} participants failed.".format(
                num_completed_participants+1,
                exp.networks()[0].max_size,
                len(exp.networks()[0].nodes(status="failed"))), end="\r")
            sys.stdout.flush()

            p_uuid = str(random.random())
            p_uuids.append(p_uuid)
            p_start_time = timenow()

            while True:
                try:
                    assign_start_time = timenow()
                    agent = exp.assign_agent_to_participant(participant_uuid=p_uuid)
                    assign_stop_time = timenow()
                    assign_time += (assign_stop_time - assign_start_time)
                except:
                    # print(traceback.format_exc())
                    break
                else:
                    process_start_time = timenow()
                    agent.receive()
                    if num_completed_participants == 0:
                        current_state = float(agent.network.nodes(type=Environment)[0].infos(type=State)[-1].contents)
                        exp.information_creation_trigger(Meme(origin=agent, contents=round(current_state)))
                    else:
                        exp.information_creation_trigger(Meme(origin=agent, contents=1))
                    process_stop_time = timenow()
                    process_time += (process_stop_time - process_start_time)
            bonus = exp.bonus(participant_uuid=p_uuid)
            assert bonus >= 0.0
            assert bonus <= exp.bonus_payment

            exp.participant_attention_check(participant_uuid=p_uuid)
            p_stop_time = timenow()
            p_times.append(p_stop_time - p_start_time)

        print("Running simulated experiment...      done!                                      ")
        sys.stdout.flush()

        overall_stop_time = timenow()

        assert len(exp.networks()) == exp.practice_repeats + exp.experiment_repeats

        """
        TEST NODES
        """

        print("Testing nodes...", end="\r")
        sys.stdout.flush()

        for network in exp.networks():

            role = network.role

            agents = network.nodes(type=Agent)
            assert len(agents) == network.max_size

            source = network.nodes(type=Source)[0]
            assert type(source) == RogersSource

            environment = network.nodes(type=Environment)[0]
            assert type(environment) == RogersEnvironment

            if role == "practice":
                for agent in agents:
                    assert type(agent) == RogersAgentFounder
            elif role == "catch":
                for agent in agents:
                    assert type(agent) == RogersAgentFounder
            else:
                for agent in agents:
                    assert type(agent) in [RogersAgentFounder, RogersAgent]

            for agent in agents:
                position = agents.index(agent)
                if position < network.generation_size:
                    assert len(agent.neighbors(connection="from")) == 2
                    assert source in agent.neighbors(connection="from")
                    assert environment in agent.neighbors(connection="from")
                else:
                    assert len(agent.neighbors(connection="from")) == 1 + network.generation_size
                    assert environment in agent.neighbors(connection="from")
                    assert any([a.__class__ == RogersAgent for a in agent.neighbors(connection="from")]) ^ any([a.__class__ == RogersAgentFounder for a in agent.neighbors(connection="from")])

        print("Testing nodes...                     done!")
        sys.stdout.flush()

        """
        TEST VECTORS
        """

        print("Testing vectors...", end="\r")
        sys.stdout.flush()

        for network in exp.networks():
            for gen in range(network.generations-1):
                for agent in range(network.generation_size):
                    for other_agent in range(network.generation_size):
                        assert agents[gen*network.generation_size + agent].is_connected(direction="to", other_node=agents[(gen+1)*network.generation_size+other_agent])

            for agent in range(network.generation_size):
                assert source.is_connected(direction="to", other_node=agents[agent])

            for agent in agents:
                assert environment in agent.neighbors(connection="from")

            for agent in source.neighbors(connection="to"):
                assert isinstance(agent, RogersAgentFounder)

        print("Testing vectors...                   done!")
        sys.stdout.flush()

        """
        TEST INFOS
        """

        print("Testing infos...", end="\r")
        sys.stdout.flush()

        for network in exp.networks():
            agents = network.nodes(type=Agent)
            for agent in agents:
                assert len(agent.infos(type=Gene)) == 1
                assert len(agent.infos(type=LearningGene)) == 1
                assert len(agent.infos(type=Meme)) == 1
                assert len(agent.infos()) == 2

        print("Testing infos...                     done!")
        sys.stdout.flush()

        """
        TEST TRANSMISSIONS
        """

        print("Testing transmissions...", end="\r")
        sys.stdout.flush()

        for network in exp.networks():
            agents = network.nodes(type=Agent)
            for agent in agents:
                in_ts = agent.transmissions(direction="incoming", status="received")
                types = [type(t.info) for t in in_ts]
                assert len(in_ts) == 2
                assert len(agent.transmissions(direction="incoming", status="pending")) == 0
                if agent.infos(type=LearningGene)[0].contents == "asocial":
                    assert State in types
                    assert LearningGene in types
                    assert Meme not in types
                else:
                    assert State not in types
                    assert LearningGene in types
                    assert Meme in types

        print("Testing transmissions...             done!")

        """
        TEST FITNESS
        """

        print("Testing fitness...", end="\r")
        sys.stdout.flush()

        p0_nodes = [n.nodes(participant_uuid=p_uuids[0])[0] for n in exp.networks()]

        is_asocial = True
        e = 2
        b = 1
        c = 0.3*b
        baseline = c+0.0001

        for n in p0_nodes:
            assert n.fitness == (baseline + 1 * b - is_asocial * c) ** e

        for network in exp.networks():
            for agent in network.nodes(type=Agent):
                is_asocial = (agent.infos(type=LearningGene)[0].contents == "asocial")
                assert agent.fitness == ((baseline + agent.score()*b - is_asocial*c) ** e)

        print("Testing fitness...                   done!")
        sys.stdout.flush()

        """
        TEST BONUS
        """

        print("Testing bonus payments...", end="\r")
        sys.stdout.flush()

        assert exp.bonus(participant_uuid=p_uuids[0]) == exp.bonus_payment

        print("Testing bonus payments...            done!")
        sys.stdout.flush()

        print("All tests passed: good job!")

        print("Test timings:")
        overall_time = overall_stop_time - overall_start_time
        print("Overall time to simulate experiment: {}".format(overall_time))
        setup_time = exp_setup_stop - exp_setup_start
        print("Experiment setup(): {}".format(setup_time))
        print("Experiment load: {}".format(exp_setup_stop2 - exp_setup_start2))
        print("Participant assignment: {}".format(assign_time))
        print("Participant processing: {}".format(process_time))
        for i, p in enumerate(p_times):
            print("Participant {}: {}".format(i, p))
