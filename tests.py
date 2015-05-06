from __future__ import print_function
import sys
from wallace import db
from wallace.models import Agent, Source
from wallace.information import Gene, Meme, State
from wallace.environments import Environment
from experiment import RogersExperiment, RogersAgent, RogersAgentFounder, RogersSource, RogersEnvironment, LearningGene
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

        p_uuids = []

        while not exp.is_experiment_over():

            p = len(exp.networks()[0].nodes(type=Agent))

            for agent in exp.networks()[0].nodes(type=Agent):
                if agent.status == "failed":
                    print("fbvhkjfdsbhvjkfd bhvjkfdb jvf dbhjvkf dbhvjkf svhjfks bvhfs bfghs vbfjs vfhjs vfghjsd ")

            print("Running simulated experiment... participant {} of {}, {} participants failed.".format(
                p+1,
                exp.networks()[0].max_size,
                len(exp.networks()[0].nodes(status="failed"))), end="\r")
            sys.stdout.flush()

            p_uuid = str(random.random())
            p_uuids.append(p_uuid)

            while True:
                try:
                    agent = exp.assign_agent_to_participant(participant_uuid=p_uuid)
                except:
                    break
                else:
                    current_state = float(agent.neighbors(connection="from", type=Environment)[0].infos(type=State)[-1].contents)
                    if p == 0:
                        Meme(origin=agent, contents=round(current_state))
                    else:
                        Meme(origin=agent, contents=random.choice([0, 1]))
                    agent.receive()
                    agent.calculate_fitness()

            bonus = exp.bonus(participant_uuid=p_uuid)
            assert bonus >= 0.0
            assert bonus <= exp.bonus_payment

            exp.participant_attention_check(participant_uuid=p_uuid)

        print("Running simulated experiment...      done!                                      ")
        sys.stdout.flush()

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

        for network in exp.networks():
            agents = network.nodes(type=Agent)
            for agent in agents:
                in_ts = agent.transmissions(direction="incoming", state="received")
                types = [type(t.info) for t in in_ts]
                assert len(in_ts) == 2
                assert len(agent.transmissions(direction="incoming", state="pending")) == 0
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

        """
        TEST BONUS
        """

        print("Testing bonus payments...", end="\r")

        assert exp.bonus(participant_uuid=p_uuids[0]) == exp.bonus_payment

        print("Testing bonus payments...            done!")

        print("All tests passed: good job!")
