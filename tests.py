from __future__ import print_function
import sys
#from wallace import networks, agents, db, sources, information, models, environments
from wallace import db
#from wallace.networks import DiscreteGenerational
from wallace.models import Agent, Source
from wallace.information import Gene, Meme, State
from wallace.environments import Environment
from experiment import RogersExperiment, RogersAgent, RogersAgentFounder, RogersSource, RogersEnvironment, LearningGene
#from experiment import RogersDiscreteGenerational, RogersNetworkProcess, RogersSource, RogersAgent, RogersAgentFounder, RogersEnvironment, RogersExperiment, LearningGene
#from nose.tools import assert_raises
import random


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

        print("Running simulated experiment...", end="\r")
        sys.stdout.flush()

        exp = RogersExperiment(self.db)
        net = exp.networks[0]

        num_reps = exp.num_repeats_experiment+exp.num_repeats_practice

        p_uuids = []

        for p in range(net.max_size):

            print("Running simulated experiment... participant {} of {}     ".format(p, net.max_size), end="\r")
            sys.stdout.flush()

            p_uuid = str(random.random())
            p_uuids.append(p_uuid)

            for rep in range(num_reps):
                agent = exp.assign_agent_to_participant(participant_uuid=p_uuid)

                current_state = float(agent.upstream_nodes(type=Environment)[0].infos(type=State)[-1].contents)
                if p == 0:
                    Meme(origin=agent, contents=round(current_state))
                elif p == 1:
                    Meme(origin=agent, contents=1-round(current_state))
                else:
                    Meme(origin=agent, contents=random.choice([0, 1]))
                agent.receive_all()
                agent.calculate_fitness()

        print("Running simulated experiment...      done!                        ")
        sys.stdout.flush()

        """
        TEST NODES
        """

        print("Testing nodes...", end="\r")
        sys.stdout.flush()

        for network in exp.networks:

            is_practice = exp.networks.index(network) < exp.num_repeats_practice

            agents = network.nodes(type=Agent)
            assert len(agents) == net.max_size

            source = network.nodes(type=Source)[0]
            assert type(source) == RogersSource

            environment = network.nodes(type=Environment)[0]
            assert type(environment) == RogersEnvironment

            if is_practice:
                for agent in agents:
                    assert type(agent) == RogersAgentFounder
            else:
                for agent in agents:
                    assert type(agent) in [RogersAgentFounder, RogersAgent]

            for agent in agents:
                position = agents.index(agent)
                if position < network.generation_size:
                    assert len(agent.upstream_nodes()) == 2
                    assert source in agent.upstream_nodes()
                    assert environment in agent.upstream_nodes()
                else:
                    assert len(agent.upstream_nodes()) == 1 + net.generation_size
                    assert environment in agent.upstream_nodes()
                    assert any([a.__class__ == RogersAgent for a in agent.upstream_nodes()]) ^ any([a.__class__ == RogersAgentFounder for a in agent.upstream_nodes()])

        print("Testing nodes...                     done!")
        sys.stdout.flush()

        """
        TEST VECTORS
        """

        print("Testing vectors...", end="\r")
        sys.stdout.flush()

        for gen in range(net.generations-1):
            for agent in range(net.generation_size):
                for other_agent in range(net.generation_size):
                    assert agents[gen*net.generation_size + agent].has_connection_to(agents[(gen+1)*net.generation_size+other_agent])

        for agent in range(net.generation_size):
            assert source.has_connection_to(agents[agent])

        for agent in agents:
            assert environment in agent.upstream_nodes()

        for agent in source.downstream_nodes():
            assert isinstance(agent, RogersAgentFounder)

        print("Testing vectors...                   done!")
        sys.stdout.flush()

        """
        TEST INFOS
        """

        print("Testing infos...", end="\r")
        sys.stdout.flush()

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

        for agent in agents:
            in_ts = agent.transmissions(type="incoming", status="all")
            types = [type(t.info) for t in in_ts]
            assert len(in_ts) == 3
            if agent.infos(type=LearningGene)[0].contents == "asocial":
                assert State in types
                assert LearningGene in types
                assert Meme not in types
            else:
                assert State in types
                assert LearningGene in types
                assert Meme in types

        print("Testing transmissions...             done!")

        """
        TEST FITNESS
        """

        print("Testing fitness...", end="\r")

        p0_nodes = [n.nodes_of_participant(p_uuids[0])[0] for n in exp.networks]
        p1_nodes = [n.nodes_of_participant(p_uuids[1])[0] for n in exp.networks]

        is_asocial = True
        e = 2
        b = 1
        c = 0.3*b
        baseline = c+0.0001

        for n in p0_nodes:
            assert n.fitness == (baseline + 1 * b - is_asocial * c) ** e

        for n in p1_nodes:
            assert n.fitness == (baseline - is_asocial * c) ** e

        print("Testing fitness...                   done!")

        """
        TEST BONUS
        """

        print("Testing bonus payments...", end="\r")

        assert exp.bonus(participant_uuid=p_uuids[0]) == exp.bonus_payment
        assert exp.bonus(participant_uuid=p_uuids[1]) == 0.0

        print("Testing bonus payments...            done!")

        print("All tests passed: good job!")
