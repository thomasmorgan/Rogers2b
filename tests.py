from __future__ import print_function
import sys
from wallace import db
from wallace.nodes import Agent, Source, Environment
from wallace.information import Gene, Meme, State
from wallace import models
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

        while exp.networks(full=False):

            num_completed_participants = len(exp.networks()[0].nodes(type=Agent))

            print("Running simulated experiment... participant {} of {}, {} participants failed.".format(
                num_completed_participants+1,
                exp.networks()[0].max_size,
                len(exp.networks()[0].nodes(status="failed"))),
                end="\r")
            sys.stdout.flush()

            p_uuid = str(random.random())
            p_uuids.append(p_uuid)
            p_start_time = timenow()

            while True:
                assign_start_time = timenow()
                agent = exp.assign_agent_to_participant(participant_uuid=p_uuid)
                assign_stop_time = timenow()
                assign_time += (assign_stop_time - assign_start_time)
                if agent is None:
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

        # create lists now for faster testsing:
        networkss = models.Network.query.all()
        nodess = models.Node.query.all()
        agentss = [node for node in nodess if isinstance(node, Agent)]
        sourcess = [node for node in nodess if isinstance(node, Source)]
        environmentss = [node for node in nodess if isinstance(node, Environment)]
        vectorss = models.Vector.query.all()
        infoss = models.Info.query.all()
        transmissionss = models.Transmission.query.all()
        transformationss = models.Transformation.query.all()

        """
        TEST NODES
        """

        print("Testing nodes...", end="\r")
        sys.stdout.flush()

        for network in [networkss[0]]:

            agents = [a for a in agentss if a.network_uuid == network.uuid]
            assert len(agents) == network.max_size

            source = [s for s in sourcess if s.network_uuid == network.uuid]
            assert len(source) == 1
            source = source[0]
            assert type(source) == RogersSource

            environment = [e for e in environmentss if e.network_uuid == network.uuid]
            assert len(environment) == 1
            environment = environment[0]
            assert type(environment) == RogersEnvironment

            vectors = [v for v in vectorss if v.network_uuid == network.uuid]

            role = network.role
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
                    assert len([v for v in vectors if v.destination_uuid == agent.uuid]) == 2
                    assert any([v for v in vectors if v.destination_uuid == agent.uuid and v.origin_uuid == source.uuid])
                    assert any([v for v in vectors if v.destination_uuid == agent.uuid and v.origin_uuid == environment.uuid])
                else:
                    assert len([v for v in vectors if v.destination_uuid == agent.uuid]) == 1 + network.generation_size
                    assert any([v for v in vectors if v.destination_uuid == agent.uuid and v.origin_uuid == environment.uuid])
                    assert any([v for v in vectors if v.destination_uuid == agent.uuid and (isinstance(v.origin, RogersAgent) or isinstance(v.origin, RogersAgentFounder))])

        print("Testing nodes...                     done!")
        sys.stdout.flush()

        """
        TEST VECTORS
        """

        print("Testing vectors...", end="\r")
        sys.stdout.flush()

        for network in [networkss[0]]:

            agents = [a for a in agentss if a.network_uuid == network.uuid]
            vectors = [v for v in vectorss if v.network_uuid == network.uuid]
            source = [s for s in sourcess if s.network_uuid == network.uuid][0]
            environment = [e for e in environmentss if e.network_uuid == network.uuid][0]

            for gen in range(network.generations-1):
                for agent in range(network.generation_size):
                    for other_agent in range(network.generation_size):
                        assert any([v for v in vectors if
                                    v.origin_uuid == agents[gen*network.generation_size + agent].uuid and
                                    v.destination_uuid == agents[(gen+1)*network.generation_size+other_agent].uuid])

            for agent in range(network.generation_size):
                assert len([v for v in vectors if v.origin_uuid == source.uuid and v.destination_uuid == agents[agent].uuid]) == 1

            for agent in agents:
                assert len([v for v in vectors if v.origin_uuid == environment.uuid and v.destination_uuid == agent.uuid]) == 1

            for v in [v for v in vectors if v.origin_uuid == source.uuid]:
                assert isinstance(v.destination, RogersAgentFounder)

        print("Testing vectors...                   done!")
        sys.stdout.flush()

        """
        TEST INFOS
        """

        print("Testing infos...", end="\r")
        sys.stdout.flush()

        for network in [networkss[0]]:

            agents = [a for a in agentss if a.network_uuid == network.uuid]
            vectors = [v for v in vectorss if v.network_uuid == network.uuid]
            source = [s for s in sourcess if s.network_uuid == network.uuid][0]
            environment = [e for e in environmentss if e.network_uuid == network.uuid][0]
            infos = [i for i in infoss if i.network_uuid == network.uuid]

            for agent in agents:
                assert len([i for i in infos if i.origin_uuid == agent.uuid]) == 2
                assert len([i for i in infos if i.origin_uuid == agent.uuid and isinstance(i, Gene)]) == 1
                assert len([i for i in infos if i.origin_uuid == agent.uuid and isinstance(i, LearningGene)]) == 1
                assert len([i for i in infos if i.origin_uuid == agent.uuid and isinstance(i, Meme)]) == 1

        print("Testing infos...                     done!")
        sys.stdout.flush()

        """
        TEST TRANSMISSIONS
        """

        print("Testing transmissions...", end="\r")
        sys.stdout.flush()

        for network in [networkss[0]]:

            agents = [a for a in agentss if a.network_uuid == network.uuid]
            vectors = [v for v in vectorss if v.network_uuid == network.uuid]
            source = [s for s in sourcess if s.network_uuid == network.uuid][0]
            environment = [e for e in environmentss if e.network_uuid == network.uuid][0]
            infos = [i for i in infoss if i.network_uuid == network.uuid]
            transmissions = [t for t in transmissionss if t.network_uuid == network.uuid]
            #transformations = [t for t in transformationss if t.network_uuid == network.uuid]

            for agent in agents:
                in_ts = [t for t in transmissions if t.destination_uuid == agent.uuid]
                types = [type(t.info) for t in in_ts]

                assert len(in_ts) == 2
                assert len([t for t in transmissions if t.destination_uuid == agent.uuid and t.status == "pending"]) == 0

                lg = [i for i in infos if i.origin_uuid == agent.uuid and isinstance(i, LearningGene)]
                assert len(lg) == 1
                lg = lg[0]

                if lg.contents == "asocial":
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

        p0_nodes = [n for n in nodess if n.participant_uuid == p_uuids[0]]

        assert len(p0_nodes) == len(networkss)

        is_asocial = True
        e = 2
        b = 1
        c = 0.3*b
        baseline = c+0.0001

        for n in p0_nodes:
            assert n.fitness == (baseline + 1 * b - is_asocial * c) ** e

        for network in [networkss[0]]:

            agents = [a for a in agentss if a.network_uuid == network.uuid]

            for agent in agents:
                is_asocial = [i for i in infoss if i.origin_uuid == agent.uuid and isinstance(i, LearningGene)][0].contents == "asocial"
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

        print("Timings:")
        overall_time = overall_stop_time - overall_start_time
        print("Overall time to simulate experiment: {}".format(overall_time))
        setup_time = exp_setup_stop - exp_setup_start
        print("Experiment setup(): {}".format(setup_time))
        print("Experiment load: {}".format(exp_setup_stop2 - exp_setup_start2))
        print("Participant assignment: {}".format(assign_time))
        print("Participant processing: {}".format(process_time))
        for i in range(len(p_times)):
            if i == 0:
                total_time = p_times[i]
            else:
                total_time += p_times[i]
            print("Participant {}: {}, total: {}".format(i, p_times[i], total_time))
        test = [p.total_seconds() for p in p_times]
        print(test)
