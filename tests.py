from __future__ import print_function
import sys
from wallace import db
from wallace.nodes import Agent, Source, Environment
from wallace.information import Gene, Meme, State
from wallace import models
from experiment import RogersExperiment2a, RogersAgent, RogersAgentFounder, RogersSource, RogersEnvironment, LearningGene, RogersSocialSource
import random
import traceback
from datetime import datetime


import subprocess
import re
import requests
import threading
import time


def timenow():
    """A string representing the current date and time."""
    return datetime.now()


class TestRogers(object):

#     autobots = 20

#     sandbox_output = subprocess.check_output(
#         "wallace sandbox",
#         shell=True)

#     m = re.search('Running as experiment (.*)...', sandbox_output)
#     exp_id = m.group(1)
#     url = "http://" + exp_id + ".herokuapp.com"

#     # Open the logs in the browser.
#     subprocess.call(
#         "wallace logs --app " + exp_id,
#         shell=True)

#     # methods that defines the behavior of each worker
#     def autobot(url, i):

#         time.sleep(i*2)
#         print("bot {} starting".format(i))
#         start_time = timenow()

#         current_trial = 0

#         # create participant
#         headers = {
#             'User-Agent': 'python',
#             'Content-Type': 'application/x-www-form-urlencoded',
#         }
#         args = {'hitId': 'rogers-test-hit', 'assignmentId': i, 'workerId': i, 'mode': 'sandbox'}
#         requests.get(url + '/exp', params=args, headers=headers)

#         # send AssignmentAccepted notification
#         args = {
#             'Event.1.EventType': 'AssignmentAccepted',
#             'Event.1.AssignmentId': i
#         }
#         requests.post(url + '/notifications', data=args, headers=headers)

#         # work through the trials
#         working = True
#         while working is True:
#             current_trial += 1
#             agent = None
#             transmission = None
#             information = None
#             information2 = None
#             information3 = None
#             try:
#                 args = {'unique_id': str(i) + ':' + str(i)}
#                 agent = requests.post(url + '/agents', data=args, headers=headers)
#                 working = agent.status_code == 200
#                 if working is True:
#                     agent_id = agent.json()['agents']['id']
#                     args = {'origin_id': agent_id}
#                     information = requests.get(url + '/information', params=args, headers=headers)
#                     args = {'destination_id': agent_id}
#                     transmission = requests.get(url + '/transmissions', params=args, headers=headers)
#                     information2 = requests.get(url + '/information/' + str(transmission.json()['transmissions'][0]['info_id']), params=args, headers=headers)
#                     time.sleep(1)
#                     args = {'origin_id': agent_id, 'contents': '0', 'info_type': 'meme'}
#                     information3 = requests.post(url + '/information', data=args, headers=headers)
#             except:
#                 print("critical error for bot {}".format(i))
#                 print("bot {} is on trial {}".format(i, current_trial))
#                 print("bot {} agent request: {}".format(i, agent))
#                 print("bot {} information request: {}".format(i, information))
#                 print("bot {} transmission request: {}".format(i, transmission))
#                 print("bot {} 2nd information request: {}".format(i, information2))
#                 print("bot {} 3rd information request: {}".format(i, information3))
#                 traceback.print_exc()

#         # send AssignmentSubmitted notification
#         args = {
#             'Event.1.EventType': 'AssignmentSubmitted',
#             'Event.1.AssignmentId': i
#         }
#         requests.post(url + '/notifications', data=args, headers=headers)

#         stop_time = timenow()
#         print("Bot {} finished in {}".format(i, stop_time - start_time))
#         return

#     print("countdown before starting bots...")
#     time.sleep(10)
#     print("buffer ended, bots started")

#     # create worker threads
#     threads = []
#     for i in range(autobots):
#         t = threading.Thread(target=autobot, args=(url, i, ))
#         threads.append(t)
#         t.start()

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
        exp = RogersExperiment2a(self.db)
        exp_setup_stop = timenow()

        exp_setup_start2 = timenow()
        exp = RogersExperiment2a(self.db)
        exp_setup_stop2 = timenow()

        exp.verbose = False

        p_ids = []
        p_times = []
        dum = timenow()
        assign_time = dum - dum
        process_time = dum - dum

        while exp.networks(full=False):

            num_completed_participants = len(exp.networks()[0].nodes(type=Agent))

            if p_times:
                print("Running simulated experiment... participant {} of {}, {} participants failed. Prev time: {}".format(
                    num_completed_participants+1,
                    exp.networks()[0].max_size,
                    len(exp.networks()[0].nodes(failed=True)),
                    p_times[-1]),
                    end="\r")
            else:
                print("Running simulated experiment... participant {} of {}, {} participants failed.".format(
                    num_completed_participants+1,
                    exp.networks()[0].max_size,
                    len(exp.networks()[0].nodes(failed=True))),
                    end="\r")
            sys.stdout.flush()

            p_id = str(random.random())
            p_ids.append(p_id)
            p_start_time = timenow()

            while True:
                assign_start_time = timenow()
                agent = exp.node_post_request(participant_id=p_id)
                assign_stop_time = timenow()
                assign_time += (assign_stop_time - assign_start_time)
                if agent is None:
                    break
                else:
                    process_start_time = timenow()
                    agent.receive()
                    current_state = float(agent.network.nodes(type=Environment)[0].infos(type=State)[-1].contents)
                    if current_state > 0.5:
                        right_answer = "blue"
                        wrong_answer = "yellow"
                    else:
                        right_answer = "yellow"
                        wrong_answer = "blue"
                    if num_completed_participants == 0:
                        exp.info_post_request(participant_id=p_id, node_id=agent.id, info_type=Meme, contents=right_answer)
                    else:
                        if random.random() < 0.75:
                            exp.info_post_request(participant_id=p_id, node_id=agent.id, info_type=Meme, contents=right_answer)
                        else:
                            exp.info_post_request(participant_id=p_id, node_id=agent.id, info_type=Meme, contents=wrong_answer)
                    process_stop_time = timenow()
                    process_time += (process_stop_time - process_start_time)
            bonus = 0.5  # exp.bonus(participant_id=p_id)
            assert bonus >= 0.0
            assert bonus <= exp.bonus_payment

            # exp.participant_attention_check(participant_id=p_id)
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

        for network in [exp.networks()[0]]:

            agents = network.nodes(type=Agent)
            assert len(agents) == network.max_size

            sources = network.nodes(type=Source)
            assert len(sources) == 2
            source_types = [type(s) for s in sources]
            assert RogersSource in source_types
            assert RogersSocialSource in source_types
            source = network.nodes(type=RogersSource)

            environment = network.nodes(type=Environment)
            assert len(environment) == 1
            environment = environment[0]
            assert type(environment) == RogersEnvironment

            vectors = network.vectors()

            role = network.role
            if role == "practice":
                for agent in agents:
                    assert type(agent) == RogersAgentFounder
            elif role == "catch":
                for agent in agents:
                    assert type(agent) == RogersAgentFounder
            else:
                for agent in agents:
                    if agent.generation in [0, 1, 2]:
                        assert type(agent) == RogersAgentFounder
                    else:
                        assert type(agent) == RogersAgent

            for agent in agents:
                if agent.generation == 0:
                    assert len(agent.vectors(direction="incoming")) == 2
                    assert agent.is_connected(direction="from", whom=source)
                    assert agent.is_connected(direction="from", whom=environment)
                else:
                    assert len(agent.vectors(direction="incoming")) in [2, 3]
                    assert not agent.is_connected(direction="from", whom=source)
                    assert agent.is_connected(direction="from", whom=environment)
                    assert RogersAgent in [type(a) for a in agent.neighbors(connection="from")] or\
                        RogersAgentFounder in [type(a) for a in agent.neighbors(connection="from")]

        print("Testing nodes...                     done!")
        sys.stdout.flush()

        """
        TEST VECTORS
        """

        print("Testing vectors...", end="\r")
        sys.stdout.flush()

        for network in [exp.networks()[0]]:

            agents = network.nodes(type=Agent)
            vectors = network.vectors()
            source = network.nodes(type=RogersSource)[0]
            environment = network.nodes(type=Environment)[0]

            for v in vectors:
                if isinstance(v.origin, Agent):
                    assert v.origin.generation == v.destination.generation - 1
                else:
                    assert isinstance(v.origin, Source) or isinstance(v.origin, Environment)

            for agent in agents:
                if agent.generation == 0:
                    assert len(models.Vector.query.filter_by(origin_id=source.id, destination_id=agent.id).all()) == 1
                else:
                    assert len(models.Vector.query.filter_by(origin_id=source.id, destination_id=agent.id).all()) == 0

            for agent in agents:
                assert len([v for v in vectors if v.origin_id == environment.id and v.destination_id == agent.id]) == 1

            for v in [v for v in vectors if v.origin_id == source.id]:
                assert isinstance(v.destination, RogersAgentFounder)

        print("Testing vectors...                   done!")
        sys.stdout.flush()

        """
        TEST INFOS
        """

        print("Testing infos...", end="\r")
        sys.stdout.flush()

        for network in [exp.networks()[0]]:

            agents = network.nodes(type=Agent)
            vectors = network.vectors()
            source = network.nodes(type=RogersSource)[0]
            environment = network.nodes(type=Environment)[0]
            infos = network.infos()

            for agent in agents:
                assert len([i for i in infos if i.origin_id == agent.id]) == 2
                assert len([i for i in infos if i.origin_id == agent.id and isinstance(i, Gene)]) == 1
                assert len([i for i in infos if i.origin_id == agent.id and isinstance(i, LearningGene)]) == 1
                assert len([i for i in infos if i.origin_id == agent.id and isinstance(i, Meme)]) == 1

        print("Testing infos...                     done!")
        sys.stdout.flush()

        """
        TEST TRANSMISSIONS
        """

        print("Testing transmissions...", end="\r")
        sys.stdout.flush()

        for network in [exp.networks()[0]]:

            agents = network.nodes(type=Agent)
            vectors = network.vectors()
            source = network.nodes(type=RogersSource)[0]
            environment = network.nodes(type=Environment)[0]
            infos = network.infos()
            transmissions = network.transmissions()

            for agent in agents:
                in_ts = [t for t in transmissions if t.destination_id == agent.id]
                types = [type(t.info) for t in in_ts]

                assert len(in_ts) == 2
                assert len([t for t in transmissions if t.destination_id == agent.id and t.status == "pending"]) == 0

                lg = [i for i in infos if i.origin_id == agent.id and isinstance(i, LearningGene)]
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

        p0_nodes = models.Node.query.filter_by(participant_id=p_ids[0]).all()

        assert len(p0_nodes) == len(exp.networks())

        is_asocial = True
        e = 2
        b = 1
        c = 0.3*b
        baseline = c+0.0001

        for n in p0_nodes:
            assert n.fitness == (baseline + 1 * b - is_asocial * c) ** e

        for network in [exp.networks()[0]]:

            agents = network.nodes(type=Agent)

            for agent in agents:
                is_asocial = agent.infos(type=LearningGene)[0].contents == "asocial"
                assert agent.fitness == ((baseline + agent.score*b - is_asocial*c) ** e)

        print("Testing fitness...                   done!")
        sys.stdout.flush()

        """
        TEST BONUS
        """

        print("Testing bonus payments...", end="\r")
        sys.stdout.flush()

        # assert exp.bonus(participant_id=p_ids[0]) == exp.bonus_payment

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

        print("#########")
        test = [p.total_seconds() for p in p_times]
        print(test)
